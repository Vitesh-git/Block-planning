"""
Database schema for the Automatic Block Planning System.

Entity overview
---------------
Corridor 1───* Station
Corridor 1───* MaintenanceTask   (unified feed from TMS / SMMS / TDMS)
Corridor 1───* Train             (COA timetable)
Corridor 1───* MaintenanceWindow (COA granted maintenance windows)
MaintenanceBlock 1───* BlockTask *───1 MaintenanceTask   (many-to-many join
                                                          with block-level detail)

The `MaintenanceTask` table is the normalized, department-agnostic record that
the data-integration layer produces by merging the three source feeds. It keeps
a `source_system` column so provenance is never lost.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Corridor(Base):
    __tablename__ = "corridors"

    corridor_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    electrified: Mapped[bool] = mapped_column(Boolean, default=True)
    traffic_gmt: Mapped[int] = mapped_column(Integer, default=0)  # gross MT/annum proxy

    stations: Mapped[list["Station"]] = relationship(back_populates="corridor")
    tasks: Mapped[list["MaintenanceTask"]] = relationship(back_populates="corridor")


class Station(Base):
    __tablename__ = "stations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    station_code: Mapped[str] = mapped_column(String(12), index=True)
    station_name: Mapped[str] = mapped_column(String(128))
    km_post: Mapped[float] = mapped_column(Float, default=0.0)
    corridor_id: Mapped[str] = mapped_column(ForeignKey("corridors.corridor_id"))

    corridor: Mapped["Corridor"] = relationship(back_populates="stations")


class MaintenanceTask(Base):
    """Unified maintenance task — the merge target for TMS/SMMS/TDMS feeds."""

    __tablename__ = "maintenance_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(String(32), index=True)  # e.g. TMS-00012
    source_system: Mapped[str] = mapped_column(String(8))  # TMS / SMMS / TDMS
    department: Mapped[str] = mapped_column(String(8), index=True)  # ENG / SNT / TRD

    corridor_id: Mapped[str] = mapped_column(ForeignKey("corridors.corridor_id"), index=True)
    station_code: Mapped[str] = mapped_column(String(12), index=True)
    km_post: Mapped[float] = mapped_column(Float, default=0.0)

    defect_code: Mapped[str] = mapped_column(String(48))
    description: Mapped[str] = mapped_column(Text)

    severity: Mapped[int] = mapped_column(Integer)          # 1-5
    asset_criticality: Mapped[int] = mapped_column(Integer)  # 1-5
    traffic_gmt: Mapped[int] = mapped_column(Integer, default=0)

    reported_date: Mapped[datetime] = mapped_column(Date)
    due_date: Mapped[datetime] = mapped_column(Date)
    overdue_days: Mapped[int] = mapped_column(Integer, default=0)

    estimated_duration_min: Mapped[int] = mapped_column(Integer)
    requires_traffic_block: Mapped[bool] = mapped_column(Boolean, default=True)
    gang_size: Mapped[int] = mapped_column(Integer, default=4)

    status: Mapped[str] = mapped_column(String(16), default="PENDING")

    # --- AI prioritization outputs (populated by the ML pipeline) --- #
    priority_label: Mapped[str] = mapped_column(String(12), default="", index=True)  # Critical/High/Medium/Low
    priority_score: Mapped[float] = mapped_column(Float, default=0.0)  # 0-1
    priority_explanation: Mapped[str] = mapped_column(Text, default="")

    corridor: Mapped["Corridor"] = relationship(back_populates="tasks")
    block_links: Mapped[list["BlockTask"]] = relationship(back_populates="task")


class Train(Base):
    __tablename__ = "trains"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    train_no: Mapped[str] = mapped_column(String(12), index=True)
    train_type: Mapped[str] = mapped_column(String(8))
    train_name: Mapped[str] = mapped_column(String(64))
    priority: Mapped[int] = mapped_column(Integer)  # 1 highest .. 5 freight
    corridor_id: Mapped[str] = mapped_column(ForeignKey("corridors.corridor_id"), index=True)
    service_date: Mapped[datetime] = mapped_column(Date)
    scheduled_dep: Mapped[str] = mapped_column(String(8))  # HH:MM


class MaintenanceWindow(Base):
    """A traffic block the Control Office is willing to grant on a corridor/date."""

    __tablename__ = "maintenance_windows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    corridor_id: Mapped[str] = mapped_column(ForeignKey("corridors.corridor_id"), index=True)
    date: Mapped[datetime] = mapped_column(Date, index=True)
    window_start: Mapped[str] = mapped_column(String(8))  # HH:MM
    window_end: Mapped[str] = mapped_column(String(8))
    window_type: Mapped[str] = mapped_column(String(24))  # NIGHT_BLOCK / LEAN_PERIOD
    max_block_minutes: Mapped[int] = mapped_column(Integer)


class MaintenanceBlock(Base):
    """An optimizer-produced block: a scheduled maintenance slot on a corridor
    within one granted window, aggregating one or more tasks (possibly across
    departments)."""

    __tablename__ = "maintenance_blocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    block_ref: Mapped[str] = mapped_column(String(24), index=True)  # BLK-2026-09-06-001
    corridor_id: Mapped[str] = mapped_column(ForeignKey("corridors.corridor_id"), index=True)
    date: Mapped[datetime] = mapped_column(Date, index=True)
    window_id: Mapped[int] = mapped_column(ForeignKey("maintenance_windows.id"))
    start_time: Mapped[str] = mapped_column(String(8))  # HH:MM
    end_time: Mapped[str] = mapped_column(String(8))
    planned_minutes: Mapped[int] = mapped_column(Integer, default=0)
    window_minutes: Mapped[int] = mapped_column(Integer, default=0)
    utilization: Mapped[float] = mapped_column(Float, default=0.0)  # planned/window
    departments: Mapped[str] = mapped_column(String(32), default="")  # e.g. "ENG,SNT"
    is_multi_dept: Mapped[bool] = mapped_column(Boolean, default=False)
    task_count: Mapped[int] = mapped_column(Integer, default=0)
    disruption_score: Mapped[float] = mapped_column(Float, default=0.0)
    approval_status: Mapped[str] = mapped_column(String(12), default="PENDING")  # PENDING / APPROVED / REJECTED
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    tasks: Mapped[list["BlockTask"]] = relationship(back_populates="block")


class BlockTask(Base):
    """Association between a block and a scheduled task."""

    __tablename__ = "block_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    block_id: Mapped[int] = mapped_column(ForeignKey("maintenance_blocks.id"), index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("maintenance_tasks.id"), index=True)

    block: Mapped["MaintenanceBlock"] = relationship(back_populates="tasks")
    task: Mapped["MaintenanceTask"] = relationship(back_populates="block_links")
