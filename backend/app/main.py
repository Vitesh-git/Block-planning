"""
FastAPI application entrypoint for the Automatic Block Planning System.

Run (development):
    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
import logging.handlers
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.core.config import settings
from app.core.database import init_db


def _configure_logging() -> None:
    """stdout logging by default; an optional size-capped rotating file.
    Solver output is never logged verbosely — only run metadata."""
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if settings.LOG_FILE:
        handlers.append(logging.handlers.RotatingFileHandler(
            settings.LOG_FILE, maxBytes=settings.LOG_MAX_BYTES,
            backupCount=settings.LOG_BACKUPS, encoding="utf-8"))
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )


_configure_logging()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    lifespan=lifespan,
    title=settings.APP_NAME,
    version="2.0.0",
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
