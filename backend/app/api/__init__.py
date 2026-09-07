"""API router aggregation."""

from fastapi import APIRouter

from app.api import (
    routes_blocks,
    routes_dashboard,
    routes_pipeline,
    routes_reports,
    routes_tasks,
)

api_router = APIRouter()
api_router.include_router(routes_pipeline.router)
api_router.include_router(routes_tasks.router)
api_router.include_router(routes_blocks.router)
api_router.include_router(routes_dashboard.router)
api_router.include_router(routes_reports.router)
