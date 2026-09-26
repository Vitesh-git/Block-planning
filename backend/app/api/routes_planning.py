"""Planning routes — traffic forecast, what-if simulation, live rescheduling,
plan version history and the audit trail."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import AuditEvent, MaintenanceWindow, PlanVersion, Scenario
from app.schemas.schemas import RescheduleEvent, SimulationRequest
from app.services import simulation
from app.services.governance import GovernanceError, audit_to_dict, parse_json
from app.services.rescheduling import apply_event
from app.services.traffic_forecast import corridor_outlook

router = APIRouter(tags=["planning"])


@router.get("/forecast/traffic")
def forecast_traffic(
    corridor_id: Optional[str] = Query(None, max_length=32),
    days: int = Query(7, ge=1, le=28),
    db: Session = Depends(get_db),
):
    """Passenger + goods outlook, window impact and the quietest 3-hour band."""
    return corridor_outlook(db, corridor_id, days)


@router.get("/windows")
def list_windows(corridor_id: Optional[str] = Query(None, max_length=32), db: Session = Depends(get_db)):
    q = db.query(MaintenanceWindow)
    if corridor_id:
        q = q.filter(MaintenanceWindow.corridor_id == corridor_id)
    return [
        {"id": w.id, "corridor_id": w.corridor_id, "date": str(w.date), "start": w.window_start,
         "end": w.window_end, "type": w.window_type, "status": w.status or "GRANTED"}
        for w in q.order_by(MaintenanceWindow.date, MaintenanceWindow.corridor_id, MaintenanceWindow.window_start)
    ]


@router.post("/simulate")
def simulate(req: SimulationRequest, db: Session = Depends(get_db)):
    """Run a what-if scenario in memory and compare it with the current plan
    settings. Persists nothing unless ``save`` is true."""
    return simulation.simulate(db, req)


@router.get("/scenarios")
def scenarios(db: Session = Depends(get_db)):
    return simulation.list_scenarios(db)


@router.delete("/scenarios/{scenario_id}")
def delete_scenario(scenario_id: int, db: Session = Depends(get_db)):
    row = db.get(Scenario, scenario_id)
    if not row:
        raise HTTPException(status_code=404, detail="Scenario not found")
    db.delete(row)
    db.commit()
    return {"deleted": scenario_id}


@router.post("/reschedule")
def reschedule(ev: RescheduleEvent, db: Session = Depends(get_db)):
    """Apply a live event and re-plan incrementally around approved blocks."""
    try:
        return apply_event(
            db, ev.type, actor=ev.actor, reason=ev.reason, corridor_id=ev.corridor_id,
            window_id=ev.window_id, new_minutes=ev.new_minutes, task_id=ev.task_id,
            description=ev.description, duration_min=ev.duration_min, time_limit_s=ev.time_limit_s,
        )
    except LookupError as e:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(e))
    except GovernanceError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/plan/versions")
def plan_versions(limit: int = Query(20, ge=1, le=200), db: Session = Depends(get_db)):
    rows = db.query(PlanVersion).order_by(PlanVersion.version.desc()).limit(limit).all()
    return [
        {
            "version": v.version, "previous_version": v.previous_version, "plan_id": v.plan_id,
            "trigger_event": v.trigger_event, "change_reason": v.change_reason,
            "changed_by": v.changed_by, "changed_at": v.changed_at.isoformat() if v.changed_at else None,
            "solver_status": v.solver_status, "solve_time_s": v.solve_time_s,
            "objective_value": v.objective_value, "num_variables": v.num_variables,
            "num_constraints": v.num_constraints, "blocks": v.blocks,
            "tasks_scheduled": v.tasks_scheduled, "diff": parse_json(v.diff, {}),
        }
        for v in rows
    ]


@router.get("/audit")
def audit(
    entity_type: Optional[str] = Query(None, max_length=16),
    entity_id: Optional[str] = Query(None, max_length=32),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    q = db.query(AuditEvent)
    if entity_type:
        q = q.filter(AuditEvent.entity_type == entity_type.upper())
    if entity_id:
        q = q.filter(AuditEvent.entity_id == entity_id)
    return [audit_to_dict(e) for e in q.order_by(AuditEvent.id.desc()).limit(limit)]
