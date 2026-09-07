"""
Block-planning analytics.

The heavy lifting (the constraint solve) lives in optimization.py. This module
provides the surrounding planning intelligence used by the dashboard and API:
corridor/location grouping of tasks and post-plan coverage analytics that show
how effectively multi-department work was combined into shared blocks — and how
many line possessions the optimizer saved versus naive single-department planning.
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

from app.models import BlockTask, MaintenanceBlock, MaintenanceTask, MaintenanceWindow


def group_tasks_by_corridor_location(db: Session) -> list[dict]:
    """Group pending block-requiring tasks by corridor and nearby location
    (10 km bands) — these clusters are the natural candidates to combine into a
    single block."""
    tasks = (
        db.query(MaintenanceTask)
        .filter(MaintenanceTask.status == "PENDING")
        .filter(MaintenanceTask.requires_traffic_block == True)  # noqa: E712
        .all()
    )
    groups: dict[tuple, list] = defaultdict(list)
    for t in tasks:
        band = int(t.km_post // 10)  # 10 km location band
        groups[(t.corridor_id, band)].append(t)

    out = []
    for (cor, band), items in sorted(groups.items()):
        depts = sorted(set(i.department for i in items))
        out.append(
            {
                "corridor_id": cor,
                "km_band": f"{band*10}-{band*10+10} km",
                "task_count": len(items),
                "departments": depts,
                "combinable": len(depts) > 1,
                "total_minutes": sum(i.estimated_duration_min for i in items),
                "priorities": _count([i.priority_label for i in items]),
            }
        )
    return out


def coverage_analytics(db: Session) -> dict:
    """Compute how the produced plan performs: coverage, block utilization,
    multi-department combination rate, and the line-possession saving versus a
    naive single-department plan."""
    blocks = db.query(MaintenanceBlock).all()
    scheduled = db.query(BlockTask).count()

    pending_block_tasks = (
        db.query(MaintenanceTask)
        .filter(MaintenanceTask.status.in_(["PENDING", "IN_PROGRESS"]))
        .filter(MaintenanceTask.requires_traffic_block == True)  # noqa: E712
        .count()
    )

    coverage = (scheduled / pending_block_tasks) if pending_block_tasks else 0.0
    avg_util = (sum(b.utilization for b in blocks) / len(blocks)) if blocks else 0.0
    multi = sum(1 for b in blocks if b.is_multi_dept)

    naive = _naive_block_count(db)
    optimized = len(blocks)

    return {
        "blocks_planned": optimized,
        "tasks_scheduled": scheduled,
        "block_requiring_pending": pending_block_tasks,
        "coverage_ratio": round(coverage, 3),
        "avg_block_utilization": round(avg_util, 3),
        "multi_dept_blocks": multi,
        "multi_dept_ratio": round(multi / optimized, 3) if optimized else 0.0,
        "naive_blocks": naive,
        "optimized_blocks": optimized,
        "blocks_saved_vs_naive": max(0, naive - optimized),
    }


def _naive_block_count(db: Session) -> int:
    """Naive planning = one separate line possession per (corridor, date,
    department). The optimizer combines multiple departments/locations into
    shared blocks, so the difference is the number of possessions avoided."""
    naive = set()
    for b in db.query(MaintenanceBlock).all():
        for d in b.departments.split(","):
            if d:
                naive.add((b.corridor_id, str(b.date), d))
    return len(naive)


def _count(labels):
    c = defaultdict(int)
    for l in labels:
        c[l] += 1
    return dict(c)


def _window_minutes(w) -> int:
    def m(hhmm):
        h, mm = hhmm.split(":")
        return int(h) * 60 + int(mm)
    length = m(w.window_end) - m(w.window_start)
    return length + 24 * 60 if length <= 0 else length


def unscheduled_tasks(db: Session) -> list[dict]:
    """Block-requiring pending tasks the optimizer could NOT place, each with a
    plain reason: no window on the corridor, work longer than any window, or the
    corridor's windows were full / outranked by higher-priority work."""
    scheduled = {bt.task_id for bt in db.query(BlockTask).all()}
    tasks = (
        db.query(MaintenanceTask)
        .filter(MaintenanceTask.status.in_(["PENDING", "IN_PROGRESS"]))
        .filter(MaintenanceTask.requires_traffic_block == True)  # noqa: E712
        .all()
    )
    win_by_corridor: dict[str, list[int]] = defaultdict(list)
    for w in db.query(MaintenanceWindow).all():
        win_by_corridor[w.corridor_id].append(_window_minutes(w))

    out = []
    for t in tasks:
        if t.id in scheduled:
            continue
        lengths = win_by_corridor.get(t.corridor_id, [])
        if not lengths:
            reason = "No maintenance window granted on this corridor."
        elif t.estimated_duration_min > max(lengths):
            reason = (
                f"Work needs {t.estimated_duration_min} min but the longest granted "
                f"window on this corridor is only {max(lengths)} min."
            )
        else:
            reason = "Corridor windows were full — outranked by higher-priority work."
        out.append(
            {
                "id": t.id,
                "source_id": t.source_id,
                "department": t.department,
                "corridor_id": t.corridor_id,
                "priority_label": t.priority_label,
                "priority_score": round(t.priority_score, 3),
                "estimated_duration_min": t.estimated_duration_min,
                "reason": reason,
            }
        )
    return sorted(out, key=lambda x: -x["priority_score"])
