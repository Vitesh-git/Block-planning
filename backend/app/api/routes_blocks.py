"""Maintenance block routes — the AI-generated schedule + controller sanctioning."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import BlockTask, MaintenanceBlock, MaintenanceTask
from app.schemas.schemas import ApproveAllRequest, BlockOut, BlockTaskOut, BlockUpdate, UnscheduledOut
from app.services.block_planning import unscheduled_tasks
from app.services.governance import GovernanceError, approve_all_pending, parse_json, set_block_approval

router = APIRouter(prefix="/blocks", tags=["blocks"])


def _serialize_many(db: Session, blocks: list[MaintenanceBlock]) -> list[BlockOut]:
    """Serialize blocks with two queries total (no per-task lookups)."""
    ids = [b.id for b in blocks]
    links = db.query(BlockTask).filter(BlockTask.block_id.in_(ids)).all() if ids else []
    task_ids = {l.task_id for l in links}
    tasks = {t.id: t for t in db.query(MaintenanceTask).filter(MaintenanceTask.id.in_(task_ids))} if task_ids else {}
    by_block: dict[int, list[BlockTaskOut]] = {}
    for l in links:
        t = tasks.get(l.task_id)
        if t:
            by_block.setdefault(l.block_id, []).append(BlockTaskOut(
                task_id=t.id, source_id=t.source_id, department=t.department,
                defect_code=t.defect_code, description=t.description,
                priority_label=t.priority_label, station_code=t.station_code,
                estimated_duration_min=t.estimated_duration_min,
            ))
    return [
        BlockOut(
            id=b.id, block_ref=b.block_ref, corridor_id=b.corridor_id, date=b.date,
            start_time=b.start_time, end_time=b.end_time, planned_minutes=b.planned_minutes,
            window_minutes=b.window_minutes, utilization=b.utilization,
            departments=b.departments, is_multi_dept=b.is_multi_dept,
            task_count=b.task_count, disruption_score=b.disruption_score,
            approval_status=b.approval_status or "PENDING",
            approved_by=b.approved_by or "", approved_at=b.approved_at,
            approval_note=b.approval_note or "", plan_version=b.plan_version or 0,
            explanation=parse_json(b.explanation, {}),
            tasks=by_block.get(b.id, []),
        )
        for b in blocks
    ]


@router.get("", response_model=list[BlockOut])
def list_blocks(db: Session = Depends(get_db)):
    blocks = db.query(MaintenanceBlock).order_by(
        MaintenanceBlock.date, MaintenanceBlock.corridor_id, MaintenanceBlock.start_time
    ).all()
    return _serialize_many(db, blocks)


@router.get("/unscheduled", response_model=list[UnscheduledOut])
def list_unscheduled(db: Session = Depends(get_db)):
    """Block-requiring tasks the optimizer could not place, with the reason."""
    return unscheduled_tasks(db)


@router.post("/approve-all")
def approve_all(payload: ApproveAllRequest, db: Session = Depends(get_db)):
    """Sanction every PENDING block in the current plan in one audited step."""
    return {"approved": approve_all_pending(db, payload.actor, payload.note)}


@router.get("/{block_id}", response_model=BlockOut)
def get_block(block_id: int, db: Session = Depends(get_db)):
    b = db.get(MaintenanceBlock, block_id)
    if not b:
        raise HTTPException(status_code=404, detail="Block not found")
    return _serialize_many(db, [b])[0]


@router.patch("/{block_id}", response_model=BlockOut)
def update_block(block_id: int, payload: BlockUpdate, db: Session = Depends(get_db)):
    """Sanction a block: APPROVED / REJECTED (reason required) / PENDING."""
    b = db.get(MaintenanceBlock, block_id)
    if not b:
        raise HTTPException(status_code=404, detail="Block not found")
    try:
        set_block_approval(db, b, payload.approval_status, payload.actor, payload.note)
    except GovernanceError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    return _serialize_many(db, [b])[0]
