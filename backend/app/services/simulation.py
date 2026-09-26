"""
What-if simulation — runs entirely in memory.

    current data ─► in-memory copy ─► apply scenario changes ─► CP-SAT
                                                                  │
            baseline (same solver settings, no changes) ◄─────────┤
                                                                  ▼
                                               metrics + deltas returned

Nothing is written to the database unless the user explicitly saves the
scenario, and then only its parameters and resulting metrics (no plan copy).
The baseline solve is cached in memory (a handful of entries) keyed on the
current data, so comparing several scenarios only pays for the scenario solve.
"""

from __future__ import annotations

import json
from collections import OrderedDict
from types import SimpleNamespace

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import BlockTask, MaintenanceBlock, MaintenanceTask, MaintenanceWindow, Scenario
from app.services.governance import clean_actor
from app.services.optimization import (
    PARALLEL_GANGS,
    WEIGHT_PRESETS,
    _hhmm,
    _minutes,
    corridor_traffic_map,
    current_version,
    forecast_disruption,
    granted_windows,
    optimize_blocks,
    plannable_tasks,
    window_length,
)

_BASELINE_CACHE: "OrderedDict[tuple, dict]" = OrderedDict()
_CACHE_SIZE = 4


def _copy_task(t) -> SimpleNamespace:
    return SimpleNamespace(
        id=t.id, source_id=t.source_id, corridor_id=t.corridor_id, department=t.department,
        estimated_duration_min=t.estimated_duration_min, priority_score=float(t.priority_score),
        priority_label=t.priority_label, requires_traffic_block=t.requires_traffic_block,
    )


def _copy_window(w) -> SimpleNamespace:
    return SimpleNamespace(
        id=w.id, corridor_id=w.corridor_id, date=w.date, window_start=w.window_start,
        window_end=w.window_end, window_type=w.window_type, max_block_minutes=w.max_block_minutes,
    )


def _snapshot(db: Session, respect_approved: bool):
    """In-memory copy of the planning problem plus the frozen approved part."""
    fixed_blocks, fixed_tasks, fixed_windows = [], set(), set()
    if respect_approved:
        fixed_blocks = db.query(MaintenanceBlock).filter(MaintenanceBlock.approval_status == "APPROVED").all()
        fixed_windows = {b.window_id for b in fixed_blocks}
        if fixed_blocks:
            fixed_tasks = {tid for (tid,) in db.query(BlockTask.task_id).filter(
                BlockTask.block_id.in_([b.id for b in fixed_blocks]))}
    tasks = [_copy_task(t) for t in plannable_tasks(db) if t.id not in fixed_tasks]
    windows = [_copy_window(w) for w in granted_windows(db) if w.id not in fixed_windows]
    fixed_task_rows = db.query(MaintenanceTask).filter(MaintenanceTask.id.in_(fixed_tasks)).all() if fixed_tasks else []
    fixed = {
        "blocks": len(fixed_blocks),
        "multi_dept": sum(1 for b in fixed_blocks if b.is_multi_dept),
        "minutes": sum(b.planned_minutes for b in fixed_blocks),
        "tasks": [_copy_task(t) for t in fixed_task_rows],
    }
    return tasks, windows, fixed


def _metrics(result, tasks, traffic: dict, fixed: dict) -> dict:
    """Plan quality metrics for (solved part + frozen approved part)."""
    all_tasks = tasks + fixed["tasks"]
    scheduled = result.scheduled_task_ids | {t.id for t in fixed["tasks"]}
    crit = [t for t in all_tasks if t.priority_label == "Critical"]
    total_w = sum(t.priority_score for t in all_tasks) or 1.0
    sched_w = sum(t.priority_score for t in all_tasks if t.id in scheduled)
    blocks = result.blocks
    pax = sum(traffic.get(b["window"].id, {}).get("pax", 0) for b in blocks)
    goods = sum(traffic.get(b["window"].id, {}).get("goods", 0) for b in blocks)
    n_blocks = len(blocks) + fixed["blocks"]
    minutes = sum(b["planned_minutes"] for b in blocks) + fixed["minutes"]
    unsched_crit = sorted((t for t in crit if t.id not in scheduled), key=lambda t: -t.priority_score)
    return {
        "solver_status": result.status,
        "solve_time_s": result.stats.get("wall_time_s", 0),
        "blocks": n_blocks,
        "tasks_scheduled": len(scheduled),
        "tasks_total": len(all_tasks),
        "coverage": round(len(scheduled) / len(all_tasks), 3) if all_tasks else 0.0,
        "priority_weighted_coverage": round(sched_w / total_w, 3),
        "critical_scheduled": sum(1 for t in crit if t.id in scheduled),
        "critical_total": len(crit),
        "multi_dept_blocks": sum(1 for b in blocks if b["is_multi_dept"]) + fixed["multi_dept"],
        "possession_minutes": int(minutes),
        "trains_affected": round(pax + goods, 1),
        "pax_trains_affected": round(pax, 1),
        "goods_trains_affected": round(goods, 1),
        "disruption_score": round(sum(b["disruption"] * b["planned_minutes"] for b in blocks), 1),
        "avg_utilization": round(sum(b["utilization"] for b in blocks) / len(blocks), 3) if blocks else 0.0,
        "unscheduled_critical": [t.source_id for t in unsched_crit[:10]],
        "by_corridor": _by_corridor(blocks),
    }


def _by_corridor(blocks) -> dict:
    out: dict[str, dict] = {}
    for b in blocks:
        c = out.setdefault(b["corridor_id"], {"blocks": 0, "tasks": 0, "minutes": 0})
        c["blocks"] += 1
        c["tasks"] += len(b["tasks"])
        c["minutes"] += b["planned_minutes"]
    return out


def _apply_changes(p, tasks, windows, db: Session):
    """Return modified copies according to the scenario parameters."""
    cancel = set(p.cancel_window_ids or [])
    scope = set(p.corridor_ids or [])
    out_w = []
    for w in windows:
        if w.id in cancel:
            continue
        if p.window_extension_min and (not scope or w.corridor_id in scope):
            new_len = max(30, window_length(w) + p.window_extension_min)
            w = SimpleNamespace(**{**vars(w), "window_end": _hhmm(_minutes(w.window_start) + new_len),
                                   "max_block_minutes": new_len})
        out_w.append(w)

    out_t = list(tasks)
    if p.extra_emergencies:
        cid = p.emergency_corridor_id
        if not cid:
            traffic = corridor_traffic_map(db)
            with_w = {w.corridor_id for w in out_w}
            cid = max(with_w or traffic, key=lambda c: traffic.get(c, 0)) if (with_w or traffic) else None
        for i in range(p.extra_emergencies):
            out_t.append(SimpleNamespace(
                id=-(i + 1), source_id=f"SIM-EMG-{i + 1}", corridor_id=cid, department="ENG",
                estimated_duration_min=int(p.emergency_duration_min), priority_score=0.95,
                priority_label="Critical", requires_traffic_block=True,
            ))
    return out_t, out_w


def _is_noop(p) -> bool:
    return (not p.window_extension_min and not p.cancel_window_ids and p.parallel_gangs == PARALLEL_GANGS
            and not p.traffic_growth_pct and not p.extra_emergencies and p.objective == "balanced")


def _data_key(db: Session, p) -> tuple:
    return (
        current_version(db),
        tuple(db.query(func.count(MaintenanceTask.id), func.max(MaintenanceTask.id),
                       func.round(func.sum(MaintenanceTask.priority_score), 3)).one()),
        db.query(func.count(MaintenanceTask.id)).filter(MaintenanceTask.status == "COMPLETED").scalar(),
        tuple(db.query(MaintenanceWindow.status, func.count(MaintenanceWindow.id))
              .group_by(MaintenanceWindow.status).order_by(MaintenanceWindow.status).all()),
        db.query(func.count(MaintenanceBlock.id)).filter(MaintenanceBlock.approval_status == "APPROVED").scalar(),
        p.respect_approved, p.time_limit_s,
    )


def simulate(db: Session, p) -> dict:
    """Run a what-if scenario. ``p`` is a SimulationRequest."""
    time_limit = p.time_limit_s or settings.SIM_TIME_LIMIT_SECONDS
    tasks, windows, fixed = _snapshot(db, p.respect_approved)
    traffic_map = corridor_traffic_map(db)

    key = _data_key(db, p)
    baseline = _BASELINE_CACHE.get(key)
    if baseline is None:
        wt = forecast_disruption(db, windows)
        res = optimize_blocks(tasks, windows, traffic_map, time_limit,
                              disruption={k: v["disruption"] for k, v in wt.items()}, deterministic=True)
        baseline = _metrics(res, tasks, wt, fixed)
        _BASELINE_CACHE[key] = baseline
        while len(_BASELINE_CACHE) > _CACHE_SIZE:
            _BASELINE_CACHE.popitem(last=False)
    else:
        _BASELINE_CACHE.move_to_end(key)

    if _is_noop(p):
        scenario = dict(baseline)  # nothing changed: identical by definition
    else:
        s_tasks, s_windows = _apply_changes(p, tasks, windows, db)
        wt = forecast_disruption(db, s_windows, p.traffic_growth_pct)
        res = optimize_blocks(
            s_tasks, s_windows, traffic_map, time_limit,
            parallel_gangs=p.parallel_gangs,
            disruption={k: v["disruption"] for k, v in wt.items()},
            weights=WEIGHT_PRESETS[p.objective],
            deterministic=True,
        )
        scenario = _metrics(res, s_tasks, wt, fixed)

    delta = {
        k: round(scenario[k] - baseline[k], 3)
        for k, v in baseline.items() if isinstance(v, (int, float)) and not isinstance(v, bool)
    }
    out = {"baseline": baseline, "scenario": scenario, "delta": delta,
           "params": p.model_dump(exclude={"save", "name"}), "saved_id": None}

    if p.save:
        out["saved_id"] = save_scenario(db, p, scenario, delta)
    return out


def save_scenario(db: Session, p, scenario: dict, delta: dict) -> int:
    name = (p.name or "").strip()[:80] or f"Scenario {db.query(Scenario).count() + 1}"
    row = Scenario(
        name=name, created_by=clean_actor(p.actor),
        params=json.dumps(p.model_dump(exclude={"save", "name", "actor"})),
        metrics=json.dumps({"scenario": {k: v for k, v in scenario.items() if k != "by_corridor"},
                            "delta": delta}),
    )
    db.add(row)
    db.flush()
    extra = db.query(Scenario.id).order_by(Scenario.id.desc()).offset(max(1, settings.SCENARIO_LIMIT)).all()
    if extra:
        db.query(Scenario).filter(Scenario.id.in_([i for (i,) in extra])).delete(synchronize_session=False)
    db.commit()
    return row.id


def list_scenarios(db: Session) -> list[dict]:
    rows = db.query(Scenario).order_by(Scenario.id.desc()).all()
    return [
        {"id": r.id, "name": r.name, "created_by": r.created_by,
         "created_at": r.created_at.isoformat() if r.created_at else None,
         "params": json.loads(r.params or "{}"), "metrics": json.loads(r.metrics or "{}")}
        for r in rows
    ]


def clear_cache() -> None:
    _BASELINE_CACHE.clear()
