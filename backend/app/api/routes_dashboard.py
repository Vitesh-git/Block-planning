"""Dashboard data routes — KPIs, charts, calendar, map."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services import dashboard as dash

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/kpis")
def kpis(db: Session = Depends(get_db)):
    return dash.kpis(db)


@router.get("/priority-distribution")
def priority_distribution(db: Session = Depends(get_db)):
    return dash.priority_distribution(db)


@router.get("/department-load")
def department_load(db: Session = Depends(get_db)):
    return dash.department_load(db)


@router.get("/block-utilization")
def block_utilization(db: Session = Depends(get_db)):
    return dash.block_utilization_series(db)


@router.get("/calendar")
def calendar(db: Session = Depends(get_db)):
    return dash.calendar(db)


@router.get("/map")
def corridor_map(db: Session = Depends(get_db)):
    return dash.corridor_map(db)


@router.get("/completion")
def completion(db: Session = Depends(get_db)):
    return dash.completion_trend(db)
