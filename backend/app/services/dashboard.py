"""Dashboard aggregation service — KPI cards, calendars, map data, charts."""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    BlockTask,
    Corridor,
    MaintenanceBlock,
    MaintenanceTask,
    Train,
)
from app.services.block_planning import coverage_analytics

# Realistic Indian Railways department display names (internal codes preserved).
DEPT_NAMES = {
    "ENG": "Engineering (P.Way)",
    "SNT": "Signal & Telecom",
    "TRD": "Traction (OHE)",
}


def kpis(db: Session) -> dict:
    total = db.query(MaintenanceTask).count()
    pending = db.query(MaintenanceTask).filter(MaintenanceTask.status == "PENDING").count()
    critical = db.query(MaintenanceTask).filter(
        MaintenanceTask.priority_label == "Critical"
    ).count()
    overdue = db.query(MaintenanceTask).filter(MaintenanceTask.overdue_days > 0).count()
    blocks = db.query(MaintenanceBlock).count()
    scheduled = db.query(BlockTask).count()

    cov = coverage_analytics(db)

    # Asset availability proxy: share of assets NOT tied up in critical/overdue
    # unresolved work, improved by planned coverage.
    unresolved_risk = critical + overdue
    base_avail = 1 - (unresolved_risk / (total or 1)) * 0.5
    planned_boost = cov["coverage_ratio"] * 0.15
    asset_availability = round(min(0.999, base_avail + planned_boost), 3)

    return {
        "total_tasks": total,
        "pending_tasks": pending,
        "critical_defects": critical,
        "overdue_tasks": overdue,
        "planned_blocks": blocks,
        "tasks_scheduled": scheduled,
        "asset_availability": asset_availability,
        "coverage_ratio": cov["coverage_ratio"],
        "multi_dept_blocks": cov["multi_dept_blocks"],
        "naive_blocks": cov["naive_blocks"],
        "optimized_blocks": cov["optimized_blocks"],
        "blocks_saved_vs_naive": cov["blocks_saved_vs_naive"],
        "avg_block_utilization": cov["avg_block_utilization"],
    }


def priority_distribution(db: Session) -> dict:
    rows = (
        db.query(MaintenanceTask.priority_label, func.count(MaintenanceTask.id))
        .group_by(MaintenanceTask.priority_label)
        .all()
    )
    order = ["Critical", "High", "Medium", "Low"]
    d = {k: 0 for k in order}
    for label, cnt in rows:
        if label in d:
            d[label] = cnt
    return d


def department_load(db: Session) -> dict:
    rows = (
        db.query(MaintenanceTask.department, func.count(MaintenanceTask.id))
        .filter(MaintenanceTask.status == "PENDING")
        .group_by(MaintenanceTask.department)
        .all()
    )
    return {DEPT_NAMES.get(k, k): v for k, v in rows}


def block_utilization_series(db: Session) -> list[dict]:
    blocks = db.query(MaintenanceBlock).order_by(MaintenanceBlock.date).all()
    return [
        {
            "block_ref": b.block_ref,
            "date": b.date.isoformat(),
            "corridor_id": b.corridor_id,
            "utilization": round(b.utilization, 3),
            "planned_minutes": b.planned_minutes,
            "window_minutes": b.window_minutes,
            "is_multi_dept": b.is_multi_dept,
        }
        for b in blocks
    ]


def calendar(db: Session) -> dict:
    """Blocks grouped by date for the weekly/monthly calendar view."""
    blocks = db.query(MaintenanceBlock).order_by(MaintenanceBlock.date).all()
    by_date = defaultdict(list)
    for b in blocks:
        by_date[b.date.isoformat()].append(
            {
                "block_ref": b.block_ref,
                "corridor_id": b.corridor_id,
                "start_time": b.start_time,
                "end_time": b.end_time,
                "departments": b.departments,
                "task_count": b.task_count,
                "is_multi_dept": b.is_multi_dept,
                "utilization": round(b.utilization, 3),
                "planned_minutes": b.planned_minutes,
                "window_minutes": b.window_minutes,
            }
        )
    return dict(by_date)


def corridor_map(db: Session) -> list[dict]:
    """Per-corridor status for the Leaflet map: aggregated pending load, planned
    blocks, and a status colour."""
    corridors = db.query(Corridor).all()
    out = []
    for c in corridors:
        pending = (
            db.query(MaintenanceTask)
            .filter(MaintenanceTask.corridor_id == c.corridor_id)
            .filter(MaintenanceTask.status == "PENDING")
            .count()
        )
        critical = (
            db.query(MaintenanceTask)
            .filter(MaintenanceTask.corridor_id == c.corridor_id)
            .filter(MaintenanceTask.priority_label == "Critical")
            .count()
        )
        blocks = (
            db.query(MaintenanceBlock)
            .filter(MaintenanceBlock.corridor_id == c.corridor_id)
            .count()
        )
        # simple status: red if critical present, amber if pending>threshold
        if critical > 0:
            status = "critical"
        elif pending > 8:
            status = "attention"
        else:
            status = "normal"

        # station coordinates come from the map util (approx lat/lon per code)
        out.append(
            {
                "corridor_id": c.corridor_id,
                "name": c.name,
                "traffic_gmt": c.traffic_gmt,
                "pending": pending,
                "critical": critical,
                "planned_blocks": blocks,
                "status": status,
                "stations": [
                    {"code": s.station_code, "name": s.station_name, "km": s.km_post}
                    for s in c.stations
                ],
            }
        )
    return out


def completion_trend(db: Session) -> dict:
    """Maintenance completion status distribution for the completion chart."""
    rows = (
        db.query(MaintenanceTask.status, func.count(MaintenanceTask.id))
        .group_by(MaintenanceTask.status)
        .all()
    )
    return {k: v for k, v in rows}
