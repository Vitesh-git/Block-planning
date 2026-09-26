"""
Explainable AI + human approval.

  * ``block_explanation`` — a structured "why this block" record written when
    the optimizer creates a block (traffic forecast, priorities carried,
    departments combined, how the window compares with the alternatives).
  * Approval workflow — PENDING → APPROVED / REJECTED with the approver, time
    and note; a rejection must say why.
  * Priority overrides — a controller may change the AI priority only with a
    reason; the AI recommendation is kept alongside for comparison and the
    decision can be reverted to the AI view.
  * ``record_audit`` — append-only trail of every human decision and plan
    change (size-capped by AUDIT_RETENTION).
"""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import AuditEvent, MaintenanceBlock, MaintenanceTask
from app.services.ai_prioritization import ORDINAL as PRIORITY_SCORE

APPROVAL_STATES = {"PENDING", "APPROVED", "REJECTED"}
DEPT_NAMES = {"ENG": "Engineering", "SNT": "S&T", "TRD": "Traction"}


class GovernanceError(ValueError):
    """A request that breaks an approval / override rule (-> HTTP 400)."""


def clean_actor(actor: str | None) -> str:
    a = (actor or "").strip()[:64]
    return a or "controller"


# --------------------------------------------------------------------------- #
# Audit trail
# --------------------------------------------------------------------------- #
def record_audit(db: Session, actor: str, entity_type: str, entity_id, action: str,
                 before: str = "", after: str = "", note: str = "") -> AuditEvent:
    ev = AuditEvent(
        actor=clean_actor(actor), entity_type=entity_type, entity_id=str(entity_id),
        action=action, before=str(before)[:64], after=str(after)[:64], note=(note or "")[:1000],
    )
    db.add(ev)
    db.flush()
    limit = max(100, settings.AUDIT_RETENTION)
    if ev.id and ev.id % 100 == 0:  # prune occasionally, not on every write
        db.query(AuditEvent).filter(AuditEvent.id <= ev.id - limit).delete(synchronize_session=False)
    return ev


def audit_to_dict(e: AuditEvent) -> dict:
    return {
        "id": e.id, "created_at": e.created_at.isoformat() if e.created_at else None,
        "actor": e.actor, "entity_type": e.entity_type, "entity_id": e.entity_id,
        "action": e.action, "before": e.before, "after": e.after, "note": e.note,
    }


# --------------------------------------------------------------------------- #
# Explanations
# --------------------------------------------------------------------------- #
def block_explanation(b: dict, traffic: dict | None, corridor_name: str,
                      corridor_disruptions: list[float], gangs: int) -> dict:
    """Build the structured explanation for one optimizer block (``b`` is an
    entry of PlanResult.blocks)."""
    w = b["window"]
    tasks = [p["task"] for p in b["tasks"]]
    labels = [getattr(t, "priority_label", "") for t in tasks]
    n_crit, n_high = labels.count("Critical"), labels.count("High")
    depts = [DEPT_NAMES.get(d, d) for d in b["departments"]]
    kind = "night block" if w.window_type == "NIGHT_BLOCK" else "lean-period block"

    reasons = []
    if n_crit or n_high:
        reasons.append(f"Carries {n_crit} Critical and {n_high} High priority task(s); "
                       f"top AI score {max(float(t.priority_score) for t in tasks):.2f}.")
    else:
        reasons.append("Uses spare window capacity for lower-priority work once urgent work was placed.")
    if len(depts) > 1:
        reasons.append(f"Combines {' + '.join(depts)} work in one possession — "
                       f"{len(depts) - 1} fewer separate line closure(s).")
    d = b["disruption"]
    ranked = sorted(corridor_disruptions)
    if traffic:
        rank = 1 + sum(1 for x in ranked if x < d)
        reasons.append(
            f"Forecast {traffic['pax']:.0f} passenger and {traffic['goods']:.0f} goods trains during the "
            f"window (disruption {d:.2f}); rank {rank} of {len(ranked)} least-disruptive windows on this corridor."
        )
    else:
        reasons.append(f"Static disruption estimate {d:.2f} ({kind}); no traffic forecast available.")
    reasons.append(f"Uses {b['planned_minutes']} of {b['window_minutes']} granted minutes "
                   f"({b['utilization']:.0%}) with up to {gangs} gangs in parallel.")

    return {
        "summary": f"{len(tasks)} task(s) ({', '.join(depts)}) in the {w.window_start}–{w.window_end} "
                   f"{kind} on {corridor_name}, {b['date']}.",
        "reasons": reasons,
        "traffic": {**(traffic or {}), "disruption": d, "source": "forecast" if traffic else "static"},
        "tasks": [
            {"task_id": p["task"].id, "priority_label": getattr(p["task"], "priority_label", ""),
             "score": round(float(p["task"].priority_score), 3),
             "offset_start": p["offset_start"], "duration": p["duration"]}
            for p in b["tasks"]
        ],
    }


def parse_json(text: str | None, default):
    if not text:
        return default
    try:
        return json.loads(text)
    except ValueError:
        return default


# --------------------------------------------------------------------------- #
# Approvals
# --------------------------------------------------------------------------- #
def set_block_approval(db: Session, block: MaintenanceBlock, status: str,
                       actor: str | None, note: str | None) -> MaintenanceBlock:
    status = (status or "").upper()
    if status not in APPROVAL_STATES:
        raise GovernanceError(f"approval_status must be one of {sorted(APPROVAL_STATES)}")
    note = (note or "").strip()
    if status == "REJECTED" and len(note) < 5:
        raise GovernanceError("A rejection needs a reason (at least 5 characters).")
    before = block.approval_status or "PENDING"
    if before == status and not note:
        return block
    block.approval_status = status
    block.approval_note = note
    if status == "PENDING":
        block.approved_by, block.approved_at = "", None
    else:
        block.approved_by, block.approved_at = clean_actor(actor), datetime.utcnow()
    record_audit(db, actor, "BLOCK", block.block_ref, status, before, status, note)
    db.commit()
    db.refresh(block)
    return block


def approve_all_pending(db: Session, actor: str | None, note: str | None) -> int:
    blocks = db.query(MaintenanceBlock).filter(MaintenanceBlock.approval_status == "PENDING").all()
    now, who = datetime.utcnow(), clean_actor(actor)
    for b in blocks:
        b.approval_status, b.approved_by, b.approved_at = "APPROVED", who, now
        b.approval_note = (note or "").strip()
    if blocks:
        record_audit(db, actor, "PLAN", "bulk", "APPROVED_ALL", "PENDING", "APPROVED",
                     f"{len(blocks)} block(s): " + ", ".join(b.block_ref for b in blocks[:20])
                     + (" …" if len(blocks) > 20 else "") + (f" — {note}" if note else ""))
    db.commit()
    return len(blocks)


def void_approval(db: Session, block: MaintenanceBlock, actor: str, why: str) -> None:
    """Called when a live event invalidates an approved block."""
    if block.approval_status != "PENDING":
        record_audit(db, actor, "BLOCK", block.block_ref, "APPROVAL_VOIDED",
                     block.approval_status, "PENDING", why)
        block.approval_status, block.approved_by, block.approved_at = "PENDING", "", None


# --------------------------------------------------------------------------- #
# Priority overrides
# --------------------------------------------------------------------------- #
def override_priority(db: Session, task: MaintenanceTask, label: str, reason: str | None,
                      actor: str | None) -> None:
    lbl = (label or "").capitalize()
    if lbl not in PRIORITY_SCORE:
        raise GovernanceError(f"priority_label must be one of {list(PRIORITY_SCORE)}")
    reason = (reason or "").strip()
    if len(reason) < 5:
        raise GovernanceError("Overriding the AI priority needs a reason (at least 5 characters).")
    before = task.priority_label
    if not task.ai_priority_label:
        task.ai_priority_label = before
    task.priority_label = lbl
    task.priority_score = PRIORITY_SCORE[lbl]
    task.priority_source = "CONTROLLER"
    task.override_reason = reason
    task.priority_explanation = (
        f"Set to {lbl} by {clean_actor(actor)} (AI recommended {task.ai_priority_label}). Reason: {reason}"
    )
    record_audit(db, actor, "TASK", task.source_id, "PRIORITY_OVERRIDE", before, lbl, reason)


def revert_to_ai(db: Session, task: MaintenanceTask, actor: str | None) -> None:
    """Drop the controller override; the next scoring pass restores AI values."""
    if (task.priority_source or "AI") != "CONTROLLER":
        return
    before = task.priority_label
    task.priority_source = "AI"
    task.override_reason = ""
    record_audit(db, actor, "TASK", task.source_id, "OVERRIDE_REVERTED", before,
                 task.ai_priority_label or "", "Reverted to the AI recommendation.")
