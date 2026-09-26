"""Pipeline routes — orchestrate ingestion, AI scoring and optimization."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import Base, engine, get_db, init_db
from app.models import (
    AuditEvent,
    BlockTask,
    Corridor,
    MaintenanceBlock,
    MaintenanceTask,
    MaintenanceWindow,
    PlanVersion,
    Station,
    Train,
)
from app.schemas.schemas import InjectRequest, PipelineRequest
from app.services import data_integration as di
from app.services import simulation, traffic_forecast
from app.services.ai_prioritization import get_prioritizer
from app.services.governance import GovernanceError, record_audit
from app.services.optimization import run_and_persist
from app.services.rescheduling import apply_event

router = APIRouter(prefix="/pipeline", tags=["pipeline"])

# Tables cleared by a full reset (order respects foreign keys). Saved what-if
# scenarios are kept: they hold only parameters + metrics.
RESET_TABLES = (BlockTask, MaintenanceBlock, PlanVersion, AuditEvent, MaintenanceTask,
                MaintenanceWindow, Train, Station, Corridor)


# Plan tables are dropped and recreated on reset, which also upgrades older
# SQLite files to never-reused ids (AUTOINCREMENT).
RECREATE_TABLES = (BlockTask, MaintenanceBlock, PlanVersion, AuditEvent)


def reset_all(db: Session) -> None:
    for model in RESET_TABLES:
        db.query(model).delete()
    db.commit()
    db.close()
    tables = [m.__table__ for m in RECREATE_TABLES]
    Base.metadata.drop_all(bind=engine, tables=tables)
    Base.metadata.create_all(bind=engine, tables=tables)
    simulation.clear_cache()


@router.post("/run")
def run_pipeline(req: PipelineRequest, db: Session = Depends(get_db)):
    """Full pipeline: (re)load data -> AI prioritization -> traffic forecast ->
    optimize blocks (plan version 1 after a reset)."""
    init_db()
    if req.reset:
        reset_all(db)

    # 1. Data integration
    merged = di.normalize_feeds()
    di.load_reference_data(db)
    di.load_tasks(db, merged)
    integ = di.integration_summary(merged)

    # 2. AI prioritization
    prio = get_prioritizer().apply_to_db(db)

    # 3. Traffic forecast (retrained on the freshly loaded running data)
    forecast = traffic_forecast.get_forecaster(db, retrain=True)

    # 4. Optimization
    if req.reset:
        record_audit(db, req.actor, "PLAN", "-", "PIPELINE_RESET", "", "", "Data reloaded and re-planned.")
    opt = run_and_persist(db, time_limit_s=req.time_limit_s, trigger="FULL_PLAN",
                          reason="Full pipeline run", actor=req.actor or "system")

    return {
        "status": "ok",
        "data_integration": integ,
        "ai_prioritization": prio,
        "traffic_forecast": forecast.info if forecast else {},
        "optimization": opt,
    }


@router.post("/prioritize")
def prioritize(db: Session = Depends(get_db)):
    return get_prioritizer().apply_to_db(db)


@router.post("/optimize")
def optimize(req: PipelineRequest, db: Session = Depends(get_db)):
    """Full re-plan of all blocks (approvals are not kept)."""
    return run_and_persist(db, time_limit_s=req.time_limit_s, trigger="FULL_PLAN",
                           reason="Manual full re-optimization", actor=req.actor or "system")


@router.post("/inject-emergency")
def inject_emergency(req: InjectRequest, db: Session = Depends(get_db)):
    """Live event shortcut: inject an urgent critical defect and re-plan
    incrementally (approved blocks stay frozen)."""
    try:
        res = apply_event(db, "EMERGENCY_DEFECT", actor=req.actor, corridor_id=req.corridor_id,
                          description=req.description, time_limit_s=req.time_limit_s)
    except LookupError as e:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(e))
    except GovernanceError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    ev = res["event"]
    return {
        "status": "ok",
        "injected": {k: ev.get(k) for k in ("task_id", "source_id", "corridor_id", "priority_label", "priority_score")},
        "scheduled": ev.get("scheduled", False),
        "optimization": res["optimization"],
    }


# Description of the AI system, so the UI can present it honestly.
AI_ENGINE = {
    "stages": [
        {
            "name": "Explainable Priority Engine",
            "kind": "Gradient-boosted classifier (scikit-learn)",
            "role": (
                "Scores every maintenance task Critical/High/Medium/Low, shows the "
                "drivers behind each decision, applies a transparent safety rule, "
                "and keeps controller overrides (with reasons) on record."
            ),
        },
        {
            "name": "Traffic Forecaster",
            "kind": "Poisson gradient-boosted regressor",
            "role": (
                "Forecasts passenger and goods trains per corridor and hour, so each "
                "maintenance window is priced by the trains it would actually hold."
            ),
        },
        {
            "name": "Constraint Optimization Engine (core)",
            "kind": "Google OR-Tools CP-SAT",
            "role": (
                "The planning brain: places priority-weighted tasks into granted "
                "windows, guarantees no overlapping possessions per corridor, "
                "combines multi-department work into shared blocks, minimizes "
                "possessions and forecast traffic disruption, and re-plans live "
                "around approved blocks."
            ),
        },
    ],
}


@router.get("/model-info")
def model_info():
    p = get_prioritizer()
    meta = dict(p.meta)
    meta.pop("explain_background", None)  # internal, not useful to the UI
    meta["engine"] = AI_ENGINE
    return meta
