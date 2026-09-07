"""
Data integration layer.

Reads the four raw source feeds (TMS, SMMS, TDMS, COA), normalizes them into a
single schema, and loads the merged records into the database. This is the
"Data Integration" core module: it harmonizes heterogeneous departmental feeds
that each use different id prefixes and column names into one canonical
`MaintenanceTask` shape plus the corridor / timetable / window reference tables.
"""

from __future__ import annotations

import os
from datetime import date, datetime

import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    Corridor,
    MaintenanceTask,
    MaintenanceWindow,
    Station,
    Train,
)

# Mapping of source system -> (filename, id column, department)
SOURCE_FEEDS = {
    "TMS": ("tms_track_defects.csv", "TMS_id", "ENG"),
    "SMMS": ("smms_signal_maintenance.csv", "SMMS_id", "SNT"),
    "TDMS": ("tdms_electrical_maintenance.csv", "TDMS_id", "TRD"),
}


def _read_csv(name: str) -> pd.DataFrame:
    path = os.path.join(settings.DATA_DIR, name)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Source feed not found: {path}. Run backend/data/generate_synthetic_data.py first."
        )
    return pd.read_csv(path)


def normalize_feeds() -> pd.DataFrame:
    """Merge the three defect feeds into one normalized DataFrame."""
    frames = []
    for system, (fname, id_col, dept) in SOURCE_FEEDS.items():
        df = _read_csv(fname)
        df = df.rename(columns={id_col: "source_id"})
        df["source_system"] = system
        # department already present but enforce consistency
        df["department"] = dept
        frames.append(df)

    merged = pd.concat(frames, ignore_index=True)

    # Canonical column ordering / typing
    merged["reported_date"] = pd.to_datetime(merged["reported_date"]).dt.date
    merged["due_date"] = pd.to_datetime(merged["due_date"]).dt.date
    merged["requires_traffic_block"] = merged["requires_traffic_block"].astype(bool)
    return merged


def _parse_date(v) -> date:
    if isinstance(v, date):
        return v
    return datetime.strptime(str(v), "%Y-%m-%d").date()


def load_reference_data(db: Session):
    """Load corridors, stations, timetable, and windows from COA/master feeds."""
    stations = _read_csv("master_stations.csv")

    # Corridors
    for cor_id, grp in stations.groupby("corridor_id"):
        row = grp.iloc[0]
        if not db.get(Corridor, cor_id):
            db.add(
                Corridor(
                    corridor_id=cor_id,
                    name=row["corridor_name"],
                    electrified=bool(row["electrified"]),
                    traffic_gmt=int(row["traffic_gmt"]),
                )
            )
    db.flush()

    # Stations
    for _, row in stations.iterrows():
        db.add(
            Station(
                station_code=row["station_code"],
                station_name=row["station_name"],
                km_post=float(row["km_post"]),
                corridor_id=row["corridor_id"],
            )
        )

    # Timetable
    trains = _read_csv("coa_timetable.csv")
    for _, row in trains.iterrows():
        db.add(
            Train(
                train_no=str(row["train_no"]),
                train_type=row["train_type"],
                train_name=row["train_name"],
                priority=int(row["priority"]),
                corridor_id=row["corridor_id"],
                service_date=_parse_date(row["service_date"]),
                scheduled_dep=row["scheduled_dep"],
            )
        )

    # Maintenance windows
    windows = _read_csv("coa_maintenance_windows.csv")
    for _, row in windows.iterrows():
        db.add(
            MaintenanceWindow(
                corridor_id=row["corridor_id"],
                date=_parse_date(row["date"]),
                window_start=row["window_start"],
                window_end=row["window_end"],
                window_type=row["window_type"],
                max_block_minutes=int(row["max_block_minutes"]),
            )
        )
    db.commit()


def load_tasks(db: Session, merged: pd.DataFrame | None = None):
    """Insert normalized maintenance tasks into the DB."""
    if merged is None:
        merged = normalize_feeds()

    for _, row in merged.iterrows():
        db.add(
            MaintenanceTask(
                source_id=row["source_id"],
                source_system=row["source_system"],
                department=row["department"],
                corridor_id=row["corridor_id"],
                station_code=row["station_code"],
                km_post=float(row["km_post"]),
                defect_code=row["defect_code"],
                description=row["description"],
                severity=int(row["severity"]),
                asset_criticality=int(row["asset_criticality"]),
                traffic_gmt=int(row["traffic_gmt"]),
                reported_date=_parse_date(row["reported_date"]),
                due_date=_parse_date(row["due_date"]),
                overdue_days=int(row["overdue_days"]),
                estimated_duration_min=int(row["estimated_duration_min"]),
                requires_traffic_block=bool(row["requires_traffic_block"]),
                gang_size=int(row["gang_size"]),
                status=row["status"],
            )
        )
    db.commit()


def integration_summary(merged: pd.DataFrame) -> dict:
    """Small provenance/quality summary returned by the API."""
    return {
        "total_tasks": int(len(merged)),
        "by_source": merged["source_system"].value_counts().to_dict(),
        "by_department": merged["department"].value_counts().to_dict(),
        "by_corridor": merged["corridor_id"].value_counts().to_dict(),
        "pending": int((merged["status"] == "PENDING").sum()),
        "overdue": int((merged["overdue_days"] > 0).sum()),
    }
