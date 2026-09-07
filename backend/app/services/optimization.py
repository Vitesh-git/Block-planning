"""
Optimization engine — Automatic Block Planning with Google OR-Tools (CP-SAT).

Problem
-------
We are given a set of pending maintenance tasks (each belonging to a corridor,
a department, with an estimated duration and an AI priority score) and a set of
granted maintenance windows (per corridor, per date, with a maximum block
length). We must decide, for each task, whether and into which window to place
it — forming *maintenance blocks* — so as to:

  * maximize the AI-weighted maintenance coverage that gets scheduled,
  * schedule high-priority tasks first,
  * MINIMIZE the number of blocks (fewer line possessions),
  * combine multi-department work into the same block where feasible,
  * minimize disruption to passenger & freight traffic (prefer night blocks,
    penalize high-traffic possessions),

subject to hard constraints:

  * a task may go into at most one window, and only a window on its own corridor;
  * within a window, works run in parallel across a limited number of gangs
    (a cumulative resource) and the makespan must fit inside the granted window;
  * windows on the same corridor never overlap (guaranteed by construction —
    COA grants non-overlapping windows), so "no overlapping maintenance on the
    same corridor" holds automatically.

The model is a real constraint program solved with CP-SAT: optional interval
variables per (task, window), a cumulative capacity per window, and a weighted
multi-objective.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ortools.sat.python import cp_model
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    MaintenanceBlock,
    MaintenanceTask,
    MaintenanceWindow,
    BlockTask,
)

# ----------------------------- tunables ----------------------------------- #
PARALLEL_GANGS = 4          # simultaneous works allowed inside one block
W_PRIORITY = 1000           # reward weight for scheduling AI priority
W_BLOCK = 260               # penalty per block opened (favours fewer blocks)
W_MULTIDEPT = 180           # bonus per extra department combined into a block
W_DISRUPTION = 220          # penalty scaling for traffic disruption


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _hhmm(total_min: int) -> str:
    total_min %= 24 * 60
    return f"{total_min // 60:02d}:{total_min % 60:02d}"


def _disruption(window_type: str, traffic_gmt: int) -> float:
    """0-1 disruption factor: night blocks are cheap, lean-period on a busy
    corridor is expensive."""
    base = 0.30 if window_type == "NIGHT_BLOCK" else 0.70
    return round(min(1.0, base * (0.5 + traffic_gmt / 100.0)), 3)


@dataclass
class PlanResult:
    blocks: list = field(default_factory=list)
    scheduled_task_ids: set = field(default_factory=set)
    status: str = ""
    objective: float = 0.0
    stats: dict = field(default_factory=dict)


def optimize_blocks(
    tasks: list[MaintenanceTask],
    windows: list[MaintenanceWindow],
    corridor_traffic: dict[str, int],
    time_limit_s: int | None = None,
) -> PlanResult:
    """Run the CP-SAT block planner. `tasks` should be the block-requiring
    pending tasks to consider; `windows` the candidate granted windows."""

    model = cp_model.CpModel()

    # Only tasks that require a traffic block are placed into windows.
    tasks = [t for t in tasks if t.requires_traffic_block]

    # Index windows and precompute lengths + disruption.
    win_len = {}
    win_disruption = {}
    for w in windows:
        length = _minutes(w.window_end) - _minutes(w.window_start)
        if length <= 0:
            length += 24 * 60  # window crosses midnight
        win_len[w.id] = length
        win_disruption[w.id] = _disruption(
            w.window_type, corridor_traffic.get(w.corridor_id, 0)
        )

    # Candidate (task, window) pairs: same corridor and task fits the window.
    windows_by_corridor: dict[str, list[MaintenanceWindow]] = {}
    for w in windows:
        windows_by_corridor.setdefault(w.corridor_id, []).append(w)

    present = {}     # (t_id, w_id) -> BoolVar
    intervals = {}   # (t_id, w_id) -> OptionalIntervalVar
    ends = {}        # (t_id, w_id) -> end IntVar
    task_windows: dict[int, list[int]] = {}

    for t in tasks:
        for w in windows_by_corridor.get(t.corridor_id, []):
            L = win_len[w.id]
            dur = min(t.estimated_duration_min, L)  # clamp; block-capped works
            if dur <= 0:
                continue
            b = model.NewBoolVar(f"p_{t.id}_{w.id}")
            start = model.NewIntVar(0, L - dur, f"s_{t.id}_{w.id}")
            end = model.NewIntVar(0, L, f"e_{t.id}_{w.id}")
            iv = model.NewOptionalIntervalVar(start, dur, end, b, f"iv_{t.id}_{w.id}")
            present[(t.id, w.id)] = b
            intervals[(t.id, w.id)] = iv
            ends[(t.id, w.id)] = end
            task_windows.setdefault(t.id, []).append(w.id)

    # Each task assigned to at most one window.
    for t in tasks:
        wl = task_windows.get(t.id, [])
        if wl:
            model.Add(sum(present[(t.id, wid)] for wid in wl) <= 1)

    # Cumulative capacity per window (parallel gangs), and makespan var.
    win_makespan = {}
    used = {}
    win_task_ids: dict[int, list[int]] = {}
    for w in windows:
        ivs = [intervals[(t.id, w.id)] for t in tasks if (t.id, w.id) in intervals]
        if not ivs:
            continue
        demands = [1] * len(ivs)
        model.AddCumulative(ivs, demands, PARALLEL_GANGS)

        # window is 'used' if any task present
        u = model.NewBoolVar(f"used_{w.id}")
        pres_vars = [present[(t.id, w.id)] for t in tasks if (t.id, w.id) in present]
        win_task_ids[w.id] = [t.id for t in tasks if (t.id, w.id) in present]
        model.AddMaxEquality(u, pres_vars)
        used[w.id] = u

        # makespan of the block (max end among present intervals)
        mk = model.NewIntVar(0, win_len[w.id], f"mk_{w.id}")
        for t in tasks:
            if (t.id, w.id) in ends:
                model.Add(mk >= ends[(t.id, w.id)])
        win_makespan[w.id] = mk

    # Multi-department bonus: reward distinct departments combined in a window.
    dept_present = {}  # (w_id, dept) -> BoolVar
    multidept_terms = []
    tasks_by_id = {t.id: t for t in tasks}
    for w in windows:
        if w.id not in used:
            continue
        depts = set(tasks_by_id[tid].department for tid in win_task_ids[w.id])
        dp_vars = []
        for d in depts:
            dv = model.NewBoolVar(f"dept_{w.id}_{d}")
            member = [
                present[(tid, w.id)]
                for tid in win_task_ids[w.id]
                if tasks_by_id[tid].department == d
            ]
            model.AddMaxEquality(dv, member)
            dept_present[(w.id, d)] = dv
            dp_vars.append(dv)
        # extra departments beyond the first => coordination bonus
        n_extra = model.NewIntVar(0, len(dp_vars), f"extra_{w.id}")
        model.Add(n_extra == sum(dp_vars) - 1).OnlyEnforceIf(used[w.id])
        model.Add(n_extra == 0).OnlyEnforceIf(used[w.id].Not())
        multidept_terms.append(n_extra)

    # ----------------------------- objective ----------------------------- #
    reward_terms = []
    for t in tasks:
        for wid in task_windows.get(t.id, []):
            score = int(round(t.priority_score * 100))  # 0..100
            reward_terms.append(present[(t.id, wid)] * (W_PRIORITY * score // 100))

    block_penalty = []
    for wid, u in used.items():
        pen = int(round(W_DISRUPTION * win_disruption[wid])) + W_BLOCK
        block_penalty.append(u * pen)

    multidept_bonus = [W_MULTIDEPT * term for term in multidept_terms]

    model.Maximize(
        sum(reward_terms) - sum(block_penalty) + sum(multidept_bonus)
    )

    # ----------------------------- solve --------------------------------- #
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(
        time_limit_s or settings.OPT_TIME_LIMIT_SECONDS
    )
    solver.parameters.num_search_workers = 2  # free-tier: fewer workers = less contention
    status = solver.Solve(model)

    result = PlanResult()
    result.status = solver.StatusName(status)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return result

    result.objective = solver.ObjectiveValue()

    win_by_id = {w.id: w for w in windows}
    for wid, u in used.items():
        if solver.Value(u) == 0:
            continue
        w = win_by_id[wid]
        placed = []
        for t in tasks:
            key = (t.id, wid)
            if key in present and solver.Value(present[key]) == 1:
                s = solver.Value(intervals[key].StartExpr())
                dur = min(t.estimated_duration_min, win_len[wid])
                placed.append(
                    {
                        "task": t,
                        "offset_start": s,
                        "offset_end": s + dur,
                        "duration": dur,
                    }
                )
        if not placed:
            continue
        makespan = max(p["offset_end"] for p in placed)
        depts = sorted(set(p["task"].department for p in placed))
        base = _minutes(w.window_start)
        result.blocks.append(
            {
                "window": w,
                "corridor_id": w.corridor_id,
                "date": w.date,
                "start_time": _hhmm(base),
                "end_time": _hhmm(base + makespan),
                "planned_minutes": makespan,
                "window_minutes": win_len[wid],
                "utilization": round(makespan / win_len[wid], 3),
                "departments": depts,
                "is_multi_dept": len(depts) > 1,
                "disruption": win_disruption[wid],
                "tasks": placed,
            }
        )
        result.scheduled_task_ids.update(p["task"].id for p in placed)

    result.stats = {
        "solver_status": result.status,
        "objective": result.objective,
        "wall_time_s": round(solver.WallTime(), 2),
        "candidate_tasks": len(tasks),
        "candidate_windows": len(windows),
        "blocks_opened": len(result.blocks),
        "tasks_scheduled": len(result.scheduled_task_ids),
        "multi_dept_blocks": sum(1 for b in result.blocks if b["is_multi_dept"]),
    }
    return result


# --------------------------------------------------------------------------- #
def run_and_persist(db: Session, time_limit_s: int | None = None) -> dict:
    """Load pending tasks + windows from DB, optimize, and persist blocks."""
    # clear previous plan
    db.query(BlockTask).delete()
    db.query(MaintenanceBlock).delete()
    db.commit()

    tasks = (
        db.query(MaintenanceTask)
        .filter(MaintenanceTask.status.in_(["PENDING", "IN_PROGRESS"]))
        .filter(MaintenanceTask.requires_traffic_block == True)  # noqa: E712
        .all()
    )
    windows = db.query(MaintenanceWindow).all()
    corridor_traffic = {t.corridor_id: t.traffic_gmt for t in tasks}
    # also from windows' corridors
    from app.models import Corridor

    for c in db.query(Corridor).all():
        corridor_traffic.setdefault(c.corridor_id, c.traffic_gmt)

    result = optimize_blocks(tasks, windows, corridor_traffic, time_limit_s)

    # Persist blocks
    counter = 0
    for b in sorted(result.blocks, key=lambda x: (str(x["date"]), x["corridor_id"])):
        counter += 1
        ref = f"BLK-{b['date']}-{counter:03d}"
        disruption_score = round(b["disruption"] * b["planned_minutes"], 1)
        block = MaintenanceBlock(
            block_ref=ref,
            corridor_id=b["corridor_id"],
            date=b["date"],
            window_id=b["window"].id,
            start_time=b["start_time"],
            end_time=b["end_time"],
            planned_minutes=b["planned_minutes"],
            window_minutes=b["window_minutes"],
            utilization=b["utilization"],
            departments=",".join(b["departments"]),
            is_multi_dept=b["is_multi_dept"],
            task_count=len(b["tasks"]),
            disruption_score=disruption_score,
        )
        db.add(block)
        db.flush()
        for p in b["tasks"]:
            db.add(BlockTask(block_id=block.id, task_id=p["task"].id))
    db.commit()

    return result.stats
