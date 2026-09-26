"""Pydantic schemas for API request/response bodies."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

Actor = Optional[str]  # free-text name of the person acting (no auth in this demo)


def _json(v, default):
    if isinstance(v, str):
        try:
            return json.loads(v) if v else default
        except ValueError:
            return default
    return v if v is not None else default


class TaskOut(BaseModel):
    id: int
    source_id: str
    source_system: str
    department: str
    corridor_id: str
    station_code: str
    km_post: float
    defect_code: str
    description: str
    severity: int
    asset_criticality: int
    traffic_gmt: int
    reported_date: date
    due_date: date
    overdue_days: int
    estimated_duration_min: int
    requires_traffic_block: bool
    gang_size: int
    status: str
    priority_label: str
    priority_score: float
    priority_explanation: str
    ai_priority_label: str = ""
    priority_source: str = "AI"
    override_reason: str = ""
    priority_factors: list[dict[str, Any]] = []

    _factors = field_validator("priority_factors", mode="before")(lambda v: _json(v, []))
    _strs = field_validator("ai_priority_label", "priority_source", "override_reason", mode="before")(
        lambda v: v or "")

    class Config:
        from_attributes = True


class TaskUpdate(BaseModel):
    """Controller edits to a task: change status and/or override AI priority
    (an override requires a reason), or revert to the AI recommendation."""
    status: Optional[str] = None
    priority_label: Optional[str] = None
    override_reason: Optional[str] = Field(None, max_length=500)
    revert_to_ai: bool = False
    actor: Actor = Field(None, max_length=64)


class CorridorOut(BaseModel):
    corridor_id: str
    name: str
    electrified: bool
    traffic_gmt: int

    class Config:
        from_attributes = True


class BlockTaskOut(BaseModel):
    task_id: int
    source_id: str
    department: str
    defect_code: str
    description: str
    priority_label: str
    station_code: str
    estimated_duration_min: int

    class Config:
        from_attributes = True


class BlockOut(BaseModel):
    id: int
    block_ref: str
    corridor_id: str
    date: date
    start_time: str
    end_time: str
    planned_minutes: int
    window_minutes: int
    utilization: float
    departments: str
    is_multi_dept: bool
    task_count: int
    disruption_score: float
    approval_status: str = "PENDING"
    approved_by: str = ""
    approved_at: Optional[datetime] = None
    approval_note: str = ""
    plan_version: int = 0
    explanation: dict[str, Any] = {}
    tasks: list[BlockTaskOut] = []

    class Config:
        from_attributes = True


class BlockUpdate(BaseModel):
    """Controller sanction decision on a planned block. REJECTED needs a note."""
    approval_status: str  # PENDING / APPROVED / REJECTED
    note: Optional[str] = Field(None, max_length=1000)
    actor: Actor = Field(None, max_length=64)


class ApproveAllRequest(BaseModel):
    note: Optional[str] = Field(None, max_length=1000)
    actor: Actor = Field(None, max_length=64)


class UnscheduledOut(BaseModel):
    id: int
    source_id: str
    department: str
    corridor_id: str
    priority_label: str
    priority_score: float
    estimated_duration_min: int
    reason: str


TimeLimit = Optional[int]


class PipelineRequest(BaseModel):
    reset: bool = True
    time_limit_s: TimeLimit = Field(None, ge=1, le=120)
    actor: Actor = Field(None, max_length=64)


class InjectRequest(BaseModel):
    """Live event shortcut: an emergency defect, then an incremental re-plan."""
    corridor_id: Optional[str] = Field(None, max_length=32)
    description: Optional[str] = Field(None, max_length=300)
    time_limit_s: TimeLimit = Field(None, ge=1, le=120)
    actor: Actor = Field(None, max_length=64)


class RescheduleEvent(BaseModel):
    """A live disruption. Approved blocks stay frozen unless the event breaks them."""
    type: Literal["EMERGENCY_DEFECT", "WINDOW_CANCELLED", "WINDOW_REDUCED", "TASK_COMPLETED", "REPLAN"]
    reason: Optional[str] = Field(None, max_length=500)
    actor: Actor = Field(None, max_length=64)
    corridor_id: Optional[str] = Field(None, max_length=32)
    window_id: Optional[int] = Field(None, ge=1)
    new_minutes: Optional[int] = Field(None, ge=15, le=1440)
    task_id: Optional[int] = Field(None, ge=1)
    description: Optional[str] = Field(None, max_length=300)
    duration_min: int = Field(60, ge=15, le=360)
    time_limit_s: TimeLimit = Field(None, ge=1, le=120)


class SimulationRequest(BaseModel):
    """What-if parameters. Runs in memory; stored only when save=True."""
    window_extension_min: int = Field(0, ge=-120, le=240)
    corridor_ids: list[str] = Field(default_factory=list, max_length=50)
    cancel_window_ids: list[int] = Field(default_factory=list, max_length=500)
    parallel_gangs: int = Field(4, ge=1, le=12)
    traffic_growth_pct: float = Field(0, ge=-50, le=200)
    extra_emergencies: int = Field(0, ge=0, le=20)
    emergency_corridor_id: Optional[str] = Field(None, max_length=32)
    emergency_duration_min: int = Field(90, ge=15, le=360)
    objective: Literal["balanced", "max_coverage", "min_disruption"] = "balanced"
    respect_approved: bool = True
    time_limit_s: TimeLimit = Field(None, ge=1, le=30)
    save: bool = False
    name: Optional[str] = Field(None, max_length=80)
    actor: Actor = Field(None, max_length=64)
