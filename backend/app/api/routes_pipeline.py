"""Pipeline routes — orchestrate ingestion, AI scoring and optimization."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db, init_db
from app.models import (
    BlockTask,
    Corridor,
    MaintenanceBlock,
    MaintenanceTask,
    MaintenanceWindow,
    Station,
    Train,
)
from app.schemas.schemas import InjectRequest, PipelineRequest
from app.services import data_integration as di
from app.services.ai_prioritization import get_prioritizer
from app.services.optimization import run_and_persist

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


@router.post("/run")
def run_pipeline(req: PipelineRequest, db: Session = Depends(get_db)):
    """Full pipeline: (re)load data -> AI prioritization -> optimize blocks."""
    init_db()

    if req.reset:
        for model in (BlockTask, MaintenanceBlock, MaintenanceTask,
                      MaintenanceWindow, Train, Station, Corridor):
            db.query(model).delete()
        db.commit()

    # 1. Data integration
    merged = di.normalize_feeds()
    di.load_reference_data(db)
    di.load_tasks(db, merged)
    integ = di.integration_summary(merged)

    # 2. AI prioritization
    prio = get_prioritizer().apply_to_db(db)

    # 3. Optimization
    opt = run_and_persist(db, time_limit_s=req.time_limit_s)

    return {
        "status": "ok",
        "data_integration": integ,
        "ai_prioritization": prio,
        "optimization": opt,
    }


@router.post("/prioritize")
def prioritize(db: Session = Depends(get_db)):
    return get_prioritizer().apply_to_db(db)


@router.post("/optimize")
def optimize(req: PipelineRequest, db: Session = Depends(get_db)):
    return run_and_persist(db, time_limit_s=req.time_limit_s)


@router.post("/inject-emergency")
def inject_emergency(req: InjectRequest, db: Session = Depends(get_db)):
    """What-if: inject an urgent critical defect, then re-prioritize and
    re-optimize so the plan adapts live (without wiping existing data)."""
    corridor = None
    if req.corridor_id:
        corridor = db.get(Corridor, req.corridor_id)
        if not corridor:
            raise HTTPException(status_code=404, detail="Corridor not found")
    else:
        # Prefer a corridor that has a granted window (so the emergency can be
        # scheduled and the adaptation is visible), busiest first.
        with_windows = {w.corridor_id for w in db.query(MaintenanceWindow).all()}
        corridors = db.query(Corridor).order_by(Corridor.traffic_gmt.desc()).all()
        corridor = next((c for c in corridors if c.corridor_id in with_windows), None) or (corridors[0] if corridors else None)
    if not corridor:
        raise HTTPException(status_code=400, detail="No corridors loaded — run the planner first.")

    station = (
        db.query(Station).filter(Station.corridor_id == corridor.corridor_id).first()
    )
    n = db.query(MaintenanceTask).filter(MaintenanceTask.source_system == "EMG").count() + 1

    task = MaintenanceTask(
        source_id=f"EMG-{n:03d}",
        source_system="EMG",
        department="ENG",
        corridor_id=corridor.corridor_id,
        station_code=station.station_code if station else "NDLS",
        km_post=station.km_post if station else 0.0,
        defect_code="RAIL_FRACTURE",
        description=req.description or "Emergency rail fracture reported — immediate possession required.",
        severity=5,
        asset_criticality=5,
        traffic_gmt=corridor.traffic_gmt,
        reported_date=date.today(),
        due_date=date.today() - timedelta(days=2),
        overdue_days=2,
        estimated_duration_min=60,
        requires_traffic_block=True,
        gang_size=8,
        status="PENDING",
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    # Re-score everything (the new task included) and re-optimize.
    get_prioritizer().apply_to_db(db)
    opt = run_and_persist(db, time_limit_s=req.time_limit_s)
    db.refresh(task)

    scheduled_ids = {bt.task_id for bt in db.query(BlockTask).all()}

    return {
        "status": "ok",
        "injected": {
            "id": task.id,
            "source_id": task.source_id,
            "corridor_id": task.corridor_id,
            "priority_label": task.priority_label,
            "priority_score": task.priority_score,
        },
        "scheduled": task.id in scheduled_ids,
        "optimization": opt,
    }


# Description of the two-stage AI system, so the UI can present it honestly:
#   Stage 1 scores & explains priority; Stage 2 (the core) plans the blocks.
AI_ENGINE = {
    "stages": [
        {
            "name": "Explainable Priority Engine",
            "kind": "Gradient-boosted classifier",
            "role": (
                "Scores every maintenance task Critical/High/Medium/Low and "
                "generates a plain-language reason for each decision, so planners "
                "can trust and audit the ranking."
            ),
        },
        {
            "name": "Constraint Optimization Engine (core)",
            "kind": "Google OR-Tools CP-SAT",
            "role": (
                "The planning brain: places priority-weighted tasks into granted "
                "windows, guarantees no overlapping possessions per corridor, "
                "combines multi-department work into shared blocks, and minimizes "
                "the number of line possessions and traffic disruption."
            ),
        },
    ],
}


@router.get("/model-info")
def model_info():
    p = get_prioritizer()
    meta = dict(p.meta)
    meta["engine"] = AI_ENGINE
    return meta
