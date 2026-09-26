"""
Dynamic real-time rescheduling.

A live event changes the ground truth (new defect, Control withdraws or
shortens a window, work finished early). The event is applied to the existing
data, then the plan is re-optimized *incrementally*:

  * blocks a controller already APPROVED stay frozen, unless the event
    invalidates them — then their approval is voided (and audited);
  * everything else is re-planned around them;
  * one PlanVersion row records the trigger, reason, actor, solver metadata
    and a compact diff (tasks added / dropped / moved). The dataset itself is
    never copied.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import BlockTask, Corridor, MaintenanceBlock, MaintenanceTask, MaintenanceWindow, Station
from app.services.ai_prioritization import get_prioritizer
from app.services.governance import GovernanceError, clean_actor, record_audit, void_approval
from app.services.optimization import _hhmm, _minutes, run_and_persist

EVENT_TYPES = ("EMERGENCY_DEFECT", "WINDOW_CANCELLED", "WINDOW_REDUCED", "TASK_COMPLETED", "REPLAN")


def _blocks_in_window(db: Session, window_id: int) -> list[MaintenanceBlock]:
    return db.query(MaintenanceBlock).filter(MaintenanceBlock.window_id == window_id).all()


def _emergency_corridor(db: Session, corridor_id: str | None) -> Corridor:
    if corridor_id:
        c = db.get(Corridor, corridor_id)
        if not c:
            raise LookupError("Corridor not found")
        return c
    # Prefer a corridor that has a granted window (so the emergency can be
    # scheduled and the adaptation is visible), busiest first.
    with_windows = {w.corridor_id for w in db.query(MaintenanceWindow).filter(MaintenanceWindow.status == "GRANTED")}
    corridors = db.query(Corridor).order_by(Corridor.traffic_gmt.desc()).all()
    c = next((c for c in corridors if c.corridor_id in with_windows), None) or (corridors[0] if corridors else None)
    if not c:
        raise GovernanceError("No corridors loaded — run the planner first.")
    return c


def apply_event(
    db: Session,
    event_type: str,
    *,
    actor: str | None = None,
    reason: str | None = None,
    corridor_id: str | None = None,
    window_id: int | None = None,
    new_minutes: int | None = None,
    task_id: int | None = None,
    description: str | None = None,
    duration_min: int = 60,
    time_limit_s: int | None = None,
) -> dict:
    """Apply one live event and re-plan. Raises LookupError (404) or
    GovernanceError (400) for bad input."""
    et = (event_type or "").upper()
    if et not in EVENT_TYPES:
        raise GovernanceError(f"event type must be one of {list(EVENT_TYPES)}")
    who = clean_actor(actor)
    applied: dict = {"type": et}
    note = (reason or "").strip()

    if et == "EMERGENCY_DEFECT":
        corridor = _emergency_corridor(db, corridor_id)
        station = db.query(Station).filter(Station.corridor_id == corridor.corridor_id).first()
        n = db.query(MaintenanceTask).filter(MaintenanceTask.source_system == "EMG").count() + 1
        task = MaintenanceTask(
            source_id=f"EMG-{n:03d}", source_system="EMG", department="ENG",
            corridor_id=corridor.corridor_id,
            station_code=station.station_code if station else "NDLS",
            km_post=station.km_post if station else 0.0,
            defect_code="RAIL_FRACTURE",
            description=(description or "Emergency rail fracture reported — immediate possession required.")[:300],
            severity=5, asset_criticality=5, traffic_gmt=corridor.traffic_gmt,
            reported_date=date.today(), due_date=date.today() - timedelta(days=2), overdue_days=2,
            estimated_duration_min=max(15, min(int(duration_min or 60), 360)),
            requires_traffic_block=True, gang_size=8, status="PENDING",
        )
        db.add(task)
        db.flush()
        get_prioritizer().apply_to_db(db, [task])
        applied.update({"task_id": task.id, "source_id": task.source_id, "corridor_id": task.corridor_id,
                        "priority_label": task.priority_label, "priority_score": task.priority_score})
        note = note or f"Emergency defect {task.source_id} on {corridor.corridor_id}"
        record_audit(db, who, "TASK", task.source_id, "EMERGENCY_DEFECT", "", task.priority_label, note)

    elif et in ("WINDOW_CANCELLED", "WINDOW_REDUCED"):
        w = db.get(MaintenanceWindow, window_id) if window_id else None
        if not w:
            raise LookupError("Window not found")
        if (w.status or "GRANTED") != "GRANTED":
            raise GovernanceError(f"Window {w.id} is already {w.status}.")
        if et == "WINDOW_CANCELLED":
            w.status = "CANCELLED"
            for b in _blocks_in_window(db, w.id):
                void_approval(db, b, who, "Control Office cancelled the window.")
            applied.update({"window_id": w.id, "corridor_id": w.corridor_id, "date": str(w.date)})
            note = note or f"Control cancelled {w.window_start}–{w.window_end} on {w.corridor_id} {w.date}"
            record_audit(db, who, "WINDOW", w.id, "WINDOW_CANCELLED", "GRANTED", "CANCELLED", note)
        else:
            old_len = _minutes(w.window_end) - _minutes(w.window_start)
            old_len = old_len + 1440 if old_len <= 0 else old_len
            minutes = int(new_minutes or 0)
            if not (15 <= minutes < old_len):
                raise GovernanceError(f"new_minutes must be between 15 and {old_len - 1} for this window.")
            old_end = w.window_end
            w.window_end = _hhmm(_minutes(w.window_start) + minutes)
            w.max_block_minutes = minutes
            for b in _blocks_in_window(db, w.id):
                if b.planned_minutes > minutes:
                    void_approval(db, b, who, f"Window shortened to {minutes} min; block needs {b.planned_minutes}.")
            applied.update({"window_id": w.id, "corridor_id": w.corridor_id, "date": str(w.date),
                            "window": f"{w.window_start}–{w.window_end}"})
            note = note or f"Control shortened window {w.id} to {minutes} min"
            record_audit(db, who, "WINDOW", w.id, "WINDOW_REDUCED", old_end, w.window_end, note)

    elif et == "TASK_COMPLETED":
        t = db.get(MaintenanceTask, task_id) if task_id else None
        if not t:
            raise LookupError("Task not found")
        before = t.status
        t.status = "COMPLETED"
        applied.update({"task_id": t.id, "source_id": t.source_id})
        note = note or f"{t.source_id} reported complete"
        record_audit(db, who, "TASK", t.source_id, "TASK_COMPLETED", before, "COMPLETED", note)
        # Completed work frees capacity in a pending block; approved blocks
        # are left as sanctioned (the possession was already granted).
        link = db.query(BlockTask).filter(BlockTask.task_id == t.id).first()
        if link:
            b = db.get(MaintenanceBlock, link.block_id)
            if b and b.approval_status == "APPROVED":
                db.delete(link)
                b.task_count = max(0, b.task_count - 1)
                if b.task_count == 0:  # nothing left to do: release the possession
                    void_approval(db, b, who, "All work in the block is complete.")

    else:  # REPLAN
        note = note or "Manual re-plan (approved blocks kept)"
        record_audit(db, who, "PLAN", "-", "REPLAN_REQUESTED", "", "", note)

    db.flush()
    plan = run_and_persist(db, time_limit_s=time_limit_s, keep_approved=True,
                           trigger=et, reason=note, actor=who)
    if applied.get("task_id") and et == "EMERGENCY_DEFECT":
        applied["scheduled"] = db.query(BlockTask).filter(BlockTask.task_id == applied["task_id"]).count() > 0
    return {"status": "ok", "event": applied, "optimization": plan}
