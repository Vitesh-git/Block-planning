"""
FastAPI application entrypoint for the Automatic Block Planning System.

Run (development):
    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.core.config import settings
from app.core.database import init_db

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description=(
        "Intelligent maintenance scheduling platform that maximizes railway "
        "asset availability by coordinating Engineering, S&T and Traction "
        "maintenance into optimized traffic blocks."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.on_event("startup")
def _startup():
    init_db()


@app.get("/")
def root():
    return {
        "app": settings.APP_NAME,
        "docs": "/docs",
        "api_prefix": settings.API_V1_PREFIX,
        "database": "sqlite" if settings.is_sqlite else "postgresql",
    }


@app.get("/health")
def health():
    return {"status": "healthy"}
