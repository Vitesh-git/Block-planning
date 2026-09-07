"""Maintenance block routes — the AI-generated schedule + controller sanctioning."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import BlockTask, MaintenanceBlock, MaintenanceTask
from app.schemas.schemas import BlockOut, BlockTaskOut, BlockUpdate, UnscheduledOut
from app.services.block_planning import unscheduled_tasks

router = APIRouter(prefix="/blocks", tags=["blocks"])

VALID_APPROVAL = {"PENDING", "APPROVED", "REJECTED"}


def _serialize(db: Session, b: MaintenanceBlock) -> BlockOut:
    links = db.query(BlockTask).filter(BlockTask.block_id == b.id).all()
    tasks = []
    for l in links:
        t = db.get(MaintenanceTask, l.task_id)
        if t:
            tasks.append(
                BlockTaskOut(
                    task_id=t.id,
                    source_id=t.source_id,
                    department=t.department,
                    defect_code=t.defect_code,
                    description=t.description,
                    priority_label=t.priority_label,
                    station_code=t.station_code,
                    estimated_duration_min=t.estimated_duration_min,
                )
            )
    return BlockOut(
        id=b.id, block_ref=b.block_ref, corridor_id=b.corridor_id, date=b.date,
        start_time=b.start_time, end_time=b.end_time, planned_minutes=b.planned_minutes,
        window_minutes=b.window_minutes, utilization=b.utilization,
        departments=b.departments, is_multi_dept=b.is_multi_dept,
        task_count=b.task_count, disruption_score=b.disruption_score,
        approval_status=getattr(b, "approval_status", "PENDING") or "PENDING",
        tasks=tasks,
    )


@router.get("", response_model=list[BlockOut])
def list_blocks(db: Session = Depends(get_db)):
    blocks = db.query(MaintenanceBlock).order_by(
        MaintenanceBlock.date, MaintenanceBlock.corridor_id
    ).all()
    return [_serialize(db, b) for b in blocks]


@router.get("/unscheduled", response_model=list[UnscheduledOut])
def list_unscheduled(db: Session = Depends(get_db)):
    """Block-requiring tasks the optimizer could not place, with the reason."""
    return unscheduled_tasks(db)


@router.get("/{block_id}", response_model=BlockOut)
def get_block(block_id: int, db: Session = Depends(get_db)):
    b = db.get(MaintenanceBlock, block_id)
    if not b:
        raise HTTPException(status_code=404, detail="Block not found")
    return _serialize(db, b)


@router.patch("/{block_id}", response_model=BlockOut)
def update_block(block_id: int, payload: BlockUpdate, db: Session = Depends(get_db)):
    """Sanction a block: APPROVED / REJECTED / PENDING."""
    b = db.get(MaintenanceBlock, block_id)
    if not b:
        raise HTTPException(status_code=404, detail="Block not found")
    status = (payload.approval_status or "").upper()
    if status not in VALID_APPROVAL:
        raise HTTPException(status_code=400, detail=f"approval_status must be one of {sorted(VALID_APPROVAL)}")
    b.approval_status = status
    db.commit()
    db.refresh(b)
    return _serialize(db, b)
