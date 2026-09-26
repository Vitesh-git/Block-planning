"""Task & corridor query + edit routes."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Corridor, MaintenanceTask
from app.schemas.schemas import CorridorOut, TaskOut, TaskUpdate
from app.services.ai_prioritization import get_prioritizer
from app.services.block_planning import group_tasks_by_corridor_location
from app.services.governance import GovernanceError, override_priority, record_audit, revert_to_ai

router = APIRouter(tags=["tasks"])

VALID_STATUS = {"PENDING", "IN_PROGRESS", "COMPLETED"}


@router.get("/corridors", response_model=list[CorridorOut])
def list_corridors(db: Session = Depends(get_db)):
    return db.query(Corridor).all()


@router.get("/tasks", response_model=list[TaskOut])
def list_tasks(
    db: Session = Depends(get_db),
    department: Optional[str] = None,
    corridor_id: Optional[str] = None,
    priority: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(500, le=2000),
):
    q = db.query(MaintenanceTask)
    if department:
        q = q.filter(MaintenanceTask.department == department)
    if corridor_id:
        q = q.filter(MaintenanceTask.corridor_id == corridor_id)
    if priority:
        q = q.filter(MaintenanceTask.priority_label == priority)
    if status:
        q = q.filter(MaintenanceTask.status == status)
    q = q.order_by(MaintenanceTask.priority_score.desc())
    return q.limit(limit).all()


@router.get("/tasks/{task_id}", response_model=TaskOut)
def get_task(task_id: int, db: Session = Depends(get_db)):
    t = db.get(MaintenanceTask, task_id)
    if not t:
        raise HTTPException(status_code=404, detail="Task not found")
    return t


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def update_task(task_id: int, payload: TaskUpdate, db: Session = Depends(get_db)):
    """Controller edit: change status, override the AI priority (reason
    required), or revert to the AI recommendation. Every change is audited."""
    t = db.get(MaintenanceTask, task_id)
    if not t:
        raise HTTPException(status_code=404, detail="Task not found")
    try:
        if payload.status is not None:
            st = payload.status.upper()
            if st not in VALID_STATUS:
                raise GovernanceError(f"status must be one of {sorted(VALID_STATUS)}")
            if st != t.status:
                record_audit(db, payload.actor, "TASK", t.source_id, "STATUS", t.status, st, "")
                t.status = st

        if payload.revert_to_ai:
            revert_to_ai(db, t, payload.actor)
            get_prioritizer().apply_to_db(db, [t])  # restore AI label/score/explanation now
        elif payload.priority_label is not None and payload.priority_label.capitalize() != t.priority_label:
            override_priority(db, t, payload.priority_label, payload.override_reason, payload.actor)
    except GovernanceError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

    db.commit()
    db.refresh(t)
    return t


@router.get("/groups")
def task_groups(db: Session = Depends(get_db)):
    """Corridor/location clusters that are candidates to combine into a block."""
    return group_tasks_by_corridor_location(db)
