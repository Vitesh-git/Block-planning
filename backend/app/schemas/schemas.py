"""Pydantic schemas for API request/response bodies."""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel


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

    class Config:
        from_attributes = True


class TaskUpdate(BaseModel):
    """Controller edits to a task: change status and/or override AI priority."""
    status: Optional[str] = None
    priority_label: Optional[str] = None


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
    tasks: list[BlockTaskOut] = []

    class Config:
        from_attributes = True


class BlockUpdate(BaseModel):
    """Controller sanction decision on a planned block."""
    approval_status: str  # PENDING / APPROVED / REJECTED


class UnscheduledOut(BaseModel):
    id: int
    source_id: str
    department: str
    corridor_id: str
    priority_label: str
    priority_score: float
    estimated_duration_min: int
    reason: str


class OptimizeRequest(BaseModel):
    time_limit_s: Optional[int] = None


class PipelineRequest(BaseModel):
    reset: bool = True
    time_limit_s: Optional[int] = None


class InjectRequest(BaseModel):
    """Inject an emergency defect (what-if), then re-prioritize and re-optimize."""
    corridor_id: Optional[str] = None
    description: Optional[str] = None
    time_limit_s: Optional[int] = None
