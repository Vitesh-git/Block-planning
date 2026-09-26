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
  * minimize disruption to passenger & goods traffic — each window's cost comes
    from the traffic forecast (trains expected during the window),

subject to hard constraints:

  * a task may go into at most one window, and only a window on its own corridor;
  * a task only goes into a window long enough to hold the whole job (work is
    never silently truncated);
  * within a window, works run in parallel across a limited number of gangs
    (a cumulative resource) and the makespan must fit inside the granted window;
  * windows on the same corridor never overlap (guaranteed by construction —
    COA grants non-overlapping windows), so "no overlapping maintenance on the
    same corridor" holds automatically.

Dynamic rescheduling reuses the same model: blocks a controller has already
APPROVED are frozen (their window and tasks are removed from the problem) and
only the rest of the plan is re-optimized. Every (re)plan writes one small
PlanVersion row (solver metadata + change diff) — never the solver log.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field

from ortools.sat.python import cp_model
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    BlockTask,
    Corridor,
    MaintenanceBlock,
    MaintenanceTask,
    MaintenanceWindow,
    PlanVersion,
)

log = logging.getLogger(__name__)

# ----------------------------- tunables ----------------------------------- #
PARALLEL_GANGS = 4          # simultaneous works allowed inside one block
W_PRIORITY = 1000           # reward weight for scheduling AI priority
W_BLOCK = 260               # penalty per block opened (favours fewer blocks)
W_MULTIDEPT = 180           # bonus per extra department combined into a block
W_DISRUPTION = 220          # penalty scaling for traffic disruption
W_STABILITY = 200           # re-planning: reward keeping a task in its previous window

WEIGHT_PRESETS = {
    "balanced": {"priority": W_PRIORITY, "block": W_BLOCK, "multidept": W_MULTIDEPT, "disruption": W_DISRUPTION},
    "max_coverage": {"priority": 1400, "block": 120, "multidept": 180, "disruption": 120},
    "min_disruption": {"priority": 900, "block": 400, "multidept": 150, "disruption": 700},
}

# One plan write at a time (API threads, reschedule events, pipeline runs).
PLAN_LOCK = threading.Lock()


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _hhmm(total_min: int) -> str:
    total_min %= 24 * 60
    return f"{total_min // 60:02d}:{total_min % 60:02d}"


def window_length(w) -> int:
    length = _minutes(w.window_end) - _minutes(w.window_start)
    if length <= 0:
        length += 24 * 60  # window crosses midnight
    cap = getattr(w, "max_block_minutes", None)
    return min(length, cap) if cap else length


def static_disruption(window_type: str, traffic_gmt: int) -> float:
    """Fallback 0-1 disruption when no traffic forecast is available: night
    blocks are cheap, lean-period on a busy corridor is expensive."""
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
    tasks: list,
    windows: list,
    corridor_traffic: dict[str, int],
    time_limit_s: int | None = None,
    *,
    parallel_gangs: int = PARALLEL_GANGS,
    disruption: dict[int, float] | None = None,
    weights: dict | None = None,
    deterministic: bool = False,
    previous: dict[int, int] | None = None,
) -> PlanResult:
    """Run the CP-SAT block planner.

    ``tasks``/``windows`` may be ORM rows or any objects with the same
    attributes (the what-if simulator passes in-memory copies).
    ``disruption`` maps window id -> 0..1 cost (from the traffic forecast);
    windows missing from it fall back to :func:`static_disruption`.
    ``deterministic=True`` (used by what-if) makes repeated solves of the same
    input return the same plan, so scenario-vs-baseline deltas reflect the
    scenario, not solver timing noise.
    ``previous`` (task id -> window id) makes re-planning *stable*: keeping a
    task where it already was earns W_STABILITY, and the old plan is given to
    the solver as a hint, so a live event only moves the work it has to.
    """
    wts = {**WEIGHT_PRESETS["balanced"], **(weights or {})}
    model = cp_model.CpModel()

    # Only tasks that require a traffic block are placed into windows.
    tasks = [t for t in tasks if t.requires_traffic_block]

    win_len = {w.id: window_length(w) for w in windows}
    win_disruption = {
        w.id: (disruption or {}).get(w.id, static_disruption(w.window_type, corridor_traffic.get(w.corridor_id, 0)))
        for w in windows
    }

    windows_by_corridor: dict[str, list] = {}
    for w in windows:
        windows_by_corridor.setdefault(w.corridor_id, []).append(w)

    present = {}     # (t_id, w_id) -> BoolVar
    intervals = {}   # (t_id, w_id) -> OptionalIntervalVar
    ends = {}        # (t_id, w_id) -> end IntVar
    task_windows: dict[int, list[int]] = {}

    for t in tasks:
        dur = int(t.estimated_duration_min)
        for w in windows_by_corridor.get(t.corridor_id, []):
            L = win_len[w.id]
            if dur <= 0 or dur > L:
                continue  # job cannot be completed inside this possession
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
        if len(wl) > 1:
            model.AddAtMostOne([present[(t.id, wid)] for wid in wl])

    # Cumulative capacity per window (parallel gangs), and makespan var.
    used = {}
    win_task_ids: dict[int, list[int]] = {}
    for w in windows:
        tids = [t.id for t in tasks if (t.id, w.id) in present]
        if not tids:
            continue
        ivs = [intervals[(tid, w.id)] for tid in tids]
        model.AddCumulative(ivs, [1] * len(ivs), max(1, int(parallel_gangs)))
        u = model.NewBoolVar(f"used_{w.id}")
        model.AddMaxEquality(u, [present[(tid, w.id)] for tid in tids])
        used[w.id] = u
        win_task_ids[w.id] = tids

    # Multi-department bonus: reward distinct departments combined in a window.
    multidept_terms = []
    tasks_by_id = {t.id: t for t in tasks}
    for wid, tids in win_task_ids.items():
        depts = sorted(set(tasks_by_id[tid].department for tid in tids))
        if len(depts) < 2:
            continue
        dp_vars = []
        for d in depts:
            dv = model.NewBoolVar(f"dept_{wid}_{d}")
            model.AddMaxEquality(dv, [present[(tid, wid)] for tid in tids if tasks_by_id[tid].department == d])
            dp_vars.append(dv)
        n_extra = model.NewIntVar(0, len(dp_vars), f"extra_{wid}")
        model.Add(n_extra == sum(dp_vars) - 1).OnlyEnforceIf(used[wid])
        model.Add(n_extra == 0).OnlyEnforceIf(used[wid].Not())
        multidept_terms.append(n_extra)

    # ----------------------------- objective ----------------------------- #
    reward_terms = []
    for t in tasks:
        score = int(round(float(t.priority_score) * 100))  # 0..100
        for wid in task_windows.get(t.id, []):
            reward_terms.append(present[(t.id, wid)] * (wts["priority"] * score // 100))
    block_penalty = [
        u * (int(round(wts["disruption"] * win_disruption[wid])) + wts["block"]) for wid, u in used.items()
    ]
    multidept_bonus = [wts["multidept"] * term for term in multidept_terms]
    stability = []
    if previous:
        for key, var in present.items():
            same = previous.get(key[0]) == key[1]
            model.AddHint(var, 1 if same else 0)
            if same:
                stability.append(var * W_STABILITY)
    model.Maximize(sum(reward_terms) - sum(block_penalty) + sum(multidept_bonus) + sum(stability))

    # ----------------------------- solve --------------------------------- #
    solver = cp_model.CpSolver()
    budget = float(time_limit_s or settings.OPT_TIME_LIMIT_SECONDS)
    solver.parameters.num_search_workers = 2  # free-tier: fewer workers = less contention
    if deterministic:
        # Reproducible parallel search bounded by deterministic work units;
        # the wall-clock limit is only a safety net.
        solver.parameters.interleave_search = True
        solver.parameters.max_deterministic_time = budget * 0.2
        solver.parameters.max_time_in_seconds = budget * 3
    else:
        solver.parameters.max_time_in_seconds = budget
    solver.parameters.log_search_progress = False  # never keep verbose solver output
    status = solver.Solve(model)

    proto = model.Proto()
    result = PlanResult()
    result.status = solver.StatusName(status)
    result.stats = {
        "solver_status": result.status,
        "objective": 0.0,
        "wall_time_s": round(solver.WallTime(), 2),
        "num_variables": len(proto.variables),
        "num_constraints": len(proto.constraints),
        "candidate_tasks": len(tasks),
        "candidate_windows": len(windows),
        "blocks_opened": 0,
        "tasks_scheduled": 0,
        "multi_dept_blocks": 0,
    }
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return result

    result.objective = solver.ObjectiveValue()
    win_by_id = {w.id: w for w in windows}
    for wid, u in used.items():
        if solver.Value(u) == 0:
            continue
        w = win_by_id[wid]
        placed = []
        for tid in win_task_ids[wid]:
            key = (tid, wid)
            if solver.Value(present[key]) == 1:
                t = tasks_by_id[tid]
                s = solver.Value(intervals[key].StartExpr())
                dur = int(t.estimated_duration_min)
                placed.append({"task": t, "offset_start": s, "offset_end": s + dur, "duration": dur})
        if not placed:
            continue
        placed.sort(key=lambda p: (p["offset_start"], -float(p["task"].priority_score)))
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

    result.stats.update({
        "objective": result.objective,
        "blocks_opened": len(result.blocks),
        "tasks_scheduled": len(result.scheduled_task_ids),
        "multi_dept_blocks": sum(1 for b in result.blocks if b["is_multi_dept"]),
    })
    return result


# --------------------------------------------------------------------------- #
ACTIVE_STATUSES = ("PENDING", "IN_PROGRESS")


def plannable_tasks(db: Session):
    return (
        db.query(MaintenanceTask)
        .filter(MaintenanceTask.status.in_(ACTIVE_STATUSES))
        .filter(MaintenanceTask.requires_traffic_block == True)  # noqa: E712
        .all()
    )


def granted_windows(db: Session):
    return (
        db.query(MaintenanceWindow)
        .filter((MaintenanceWindow.status == "GRANTED") | (MaintenanceWindow.status.is_(None)))
        .all()
    )


def corridor_traffic_map(db: Session) -> dict[str, int]:
    return {c.corridor_id: c.traffic_gmt for c in db.query(Corridor).all()}


def forecast_disruption(db: Session, windows, growth_pct: float = 0.0) -> dict[int, dict]:
    """Window id -> {pax, goods, disruption}; empty dict if forecasting is
    unavailable (the optimizer then uses the static rule)."""
    from app.services.traffic_forecast import window_traffic

    try:
        return window_traffic(db, windows, growth_pct)
    except Exception:  # never let forecasting take the planner down
        log.exception("traffic forecast unavailable; using static disruption")
        return {}


def current_version(db: Session) -> int:
    v = db.query(PlanVersion).order_by(PlanVersion.version.desc()).first()
    return v.version if v else 0


def _assignment(db: Session) -> dict[int, int]:
    """task_id -> window_id for the plan currently in the database."""
    rows = (
        db.query(BlockTask.task_id, MaintenanceBlock.window_id)
        .join(MaintenanceBlock, MaintenanceBlock.id == BlockTask.block_id)
        .all()
    )
    return {tid: wid for tid, wid in rows}


def _diff(before: dict[int, int], after: dict[int, int]) -> dict:
    added = sorted(set(after) - set(before))
    dropped = sorted(set(before) - set(after))
    moved = sorted(t for t in set(before) & set(after) if before[t] != after[t])
    cap = 50  # keep version rows small
    return {
        "added": len(added), "dropped": len(dropped), "moved": len(moved),
        "unchanged": len(set(before) & set(after)) - len(moved),
        "added_ids": added[:cap], "dropped_ids": dropped[:cap], "moved_ids": moved[:cap],
    }


def run_and_persist(
    db: Session,
    time_limit_s: int | None = None,
    *,
    keep_approved: bool = False,
    trigger: str = "FULL_PLAN",
    reason: str = "",
    actor: str = "system",
) -> dict:
    """Optimize and persist the plan as a new version.

    keep_approved=False  — full re-plan: every block is regenerated.
    keep_approved=True   — dynamic rescheduling: APPROVED blocks stay frozen,
                           windows of REJECTED blocks are withdrawn, and only
                           the remaining work is re-optimized.
    """
    from app.services.governance import block_explanation, record_audit

    with PLAN_LOCK:
        before = _assignment(db)
        prev_version = current_version(db)
        version = prev_version + 1

        kept = []
        if keep_approved:
            blocks = db.query(MaintenanceBlock).all()
            for b in blocks:
                if b.approval_status == "APPROVED":
                    kept.append(b)
                elif b.approval_status == "REJECTED":
                    w = db.get(MaintenanceWindow, b.window_id)
                    if w and (w.status or "GRANTED") == "GRANTED":
                        w.status = "REJECTED"
                        record_audit(db, actor, "WINDOW", w.id, "WINDOW_WITHDRAWN", "GRANTED", "REJECTED",
                                     f"Block {b.block_ref} was rejected by the controller.")
        kept_ids = {b.id for b in kept}
        stale = [b.id for b in db.query(MaintenanceBlock.id).all() if b.id not in kept_ids]
        if stale:
            db.query(BlockTask).filter(BlockTask.block_id.in_(stale)).delete(synchronize_session="fetch")
            db.query(MaintenanceBlock).filter(MaintenanceBlock.id.in_(stale)).delete(synchronize_session="fetch")
        db.flush()

        kept_windows = {b.window_id for b in kept}
        kept_tasks = {bt.task_id for bt in db.query(BlockTask).filter(BlockTask.block_id.in_(kept_ids)).all()} if kept_ids else set()
        tasks = [t for t in plannable_tasks(db) if t.id not in kept_tasks]
        windows = [w for w in granted_windows(db) if w.id not in kept_windows]
        traffic = corridor_traffic_map(db)
        wt = forecast_disruption(db, windows)

        result = optimize_blocks(
            tasks, windows, traffic, time_limit_s,
            disruption={wid: v["disruption"] for wid, v in wt.items()},
            previous=before if keep_approved else None,
        )

        # Windows per corridor, for "why this window" comparisons.
        disr_by_corridor: dict[str, list[float]] = {}
        for w in windows:
            disr_by_corridor.setdefault(w.corridor_id, []).append(
                wt.get(w.id, {}).get("disruption", static_disruption(w.window_type, traffic.get(w.corridor_id, 0))))
        corridor_names = {c.corridor_id: c.name for c in db.query(Corridor).all()}

        # Refs carry the plan version (e.g. BLK-0906-003-v2) so a ref is never
        # reused for a different block across re-plans.
        counter = 0
        for b in sorted(result.blocks, key=lambda x: (str(x["date"]), x["corridor_id"], x["start_time"])):
            counter += 1
            ref = f"BLK-{b['date']:%m%d}-{counter:03d}-v{version}"
            explanation = block_explanation(
                b, wt.get(b["window"].id), corridor_names.get(b["corridor_id"], b["corridor_id"]),
                disr_by_corridor.get(b["corridor_id"], []), PARALLEL_GANGS,
            )
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
                disruption_score=round(b["disruption"] * b["planned_minutes"], 1),
                plan_version=version,
                explanation=json.dumps(explanation, separators=(",", ":")),
            )
            db.add(block)
            db.flush()
            for p in b["tasks"]:
                db.add(BlockTask(block_id=block.id, task_id=p["task"].id))
        db.flush()

        after = _assignment(db)
        diff = _diff(before, after)
        stats = dict(result.stats)
        stats.update({
            "blocks_opened": len(result.blocks) + len(kept),
            "tasks_scheduled": len(after),
            "kept_approved_blocks": len(kept),
            "multi_dept_blocks": stats["multi_dept_blocks"] + sum(1 for b in kept if b.is_multi_dept),
        })
        start = min((w.date for w in windows), default=None) or min((b.date for b in kept), default=None)
        db.add(PlanVersion(
            plan_id=f"PLAN-{start}" if start else "MAIN",
            version=version,
            previous_version=prev_version,
            trigger_event=trigger,
            change_reason=reason[:500],
            changed_by=actor[:64],
            solver_status=stats["solver_status"],
            solve_time_s=stats["wall_time_s"],
            objective_value=float(stats["objective"] or 0),
            num_variables=stats["num_variables"],
            num_constraints=stats["num_constraints"],
            blocks=stats["blocks_opened"],
            tasks_scheduled=stats["tasks_scheduled"],
            diff=json.dumps(diff, separators=(",", ":")),
        ))
        _prune_versions(db)
        db.commit()

        stats["version"] = version
        stats["diff"] = {k: v for k, v in diff.items() if not k.endswith("_ids")}
        log.info("plan v%s (%s): %s", version, trigger,
                 {k: stats[k] for k in ("solver_status", "wall_time_s", "blocks_opened", "tasks_scheduled")})
        return stats


def _prune_versions(db: Session) -> None:
    keep = max(1, settings.PLAN_VERSION_RETENTION)
    ids = [i for (i,) in db.query(PlanVersion.id).order_by(PlanVersion.id.desc()).offset(keep).all()]
    if ids:
        db.query(PlanVersion).filter(PlanVersion.id.in_(ids)).delete(synchronize_session=False)
