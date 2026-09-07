"""Application configuration.

Reads settings from environment variables (.env supported via pydantic-settings).
The DATABASE_URL controls whether the app runs against PostgreSQL (production,
as specified) or falls back to a local SQLite file for zero-setup development.
"""

from __future__ import annotations

import os
from functools import lru_cache

try:
    from pydantic_settings import BaseSettings
except ImportError:  # pydantic v1 fallback
    from pydantic import BaseSettings  # type: ignore


class Settings(BaseSettings):
    APP_NAME: str = "Automatic Block Planning System for Indian Railways"
    API_V1_PREFIX: str = "/api/v1"

    # ------------------------------------------------------------------ #
    # Database.
    #   * Production (as specified in the brief): PostgreSQL, e.g.
    #       postgresql+psycopg2://user:pass@localhost:5432/railway_bps
    #   * Development default: SQLite file so the stack runs with zero setup.
    # ------------------------------------------------------------------ #
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "sqlite:///" + os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "railway_bps.db"),
    )

    # Paths
    DATA_DIR: str = os.getenv(
        "DATA_DIR",
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "raw"),
    )
    MODEL_DIR: str = os.getenv(
        "MODEL_DIR",
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "ml_artifacts"),
    )

    # CORS
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")

    # Optimization defaults
    OPT_TIME_LIMIT_SECONDS: int = int(os.getenv("OPT_TIME_LIMIT_SECONDS", "20"))

    class Config:
        env_file = ".env"
        extra = "ignore"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
