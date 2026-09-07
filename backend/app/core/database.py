"""SQLAlchemy engine / session setup.

Works transparently against PostgreSQL or SQLite depending on DATABASE_URL.
SQLite needs the `check_same_thread` flag disabled so FastAPI's threadpool can
share connections; PostgreSQL uses a normal pooled engine.
"""

from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

connect_args = {}
engine_kwargs = {"pool_pre_ping": True}

if settings.is_sqlite:
    connect_args = {"check_same_thread": False}
    engine_kwargs = {}  # SQLite ignores pool sizing

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args, **engine_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def get_db():
    """FastAPI dependency that yields a scoped DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_schema():
    """Lightweight additive migration: for any table that already exists, add
    columns declared on the model but missing in the database. Lets new columns
    (e.g. block approval status) work against an older on-disk SQLite file
    without a manual migration or a re-seed."""
    try:
        insp = inspect(engine)
        existing = set(insp.get_table_names())
        for table in Base.metadata.sorted_tables:
            if table.name not in existing:
                continue  # create_all handles brand-new tables
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in have:
                    continue
                coltype = col.type.compile(dialect=engine.dialect)
                default = ""
                arg = getattr(col.default, "arg", None) if col.default is not None else None
                if arg is not None and not callable(arg):
                    if isinstance(arg, bool):
                        default = f" DEFAULT {1 if arg else 0}"
                    elif isinstance(arg, (int, float)):
                        default = f" DEFAULT {arg}"
                    elif isinstance(arg, str):
                        default = f" DEFAULT '{arg}'"
                try:
                    with engine.begin() as conn:
                        conn.execute(text(
                            f'ALTER TABLE {table.name} ADD COLUMN {col.name} {coltype}{default}'
                        ))
                except Exception:
                    pass  # column may already exist / dialect quirk — non-fatal
    except Exception:
        pass  # never block startup on the best-effort migration


def init_db():
    """Create all tables (safe to call repeatedly) and add any missing columns."""
    from app import models  # noqa: F401  (ensure models are imported/registered)

    Base.metadata.create_all(bind=engine)
    _ensure_schema()
