"""SQLModel engine and session dependency for the Postgres history store."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

logger = logging.getLogger("tracerag.database")

# load .env so APP_DATABASE_URL is available; no-op if absent
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:  # pragma: no cover
    pass

_engine = None  # lazily created


def get_engine():
    """Return the process-wide SQLModel engine, creating it on first use."""
    global _engine
    if _engine is None:
        url = os.getenv("APP_DATABASE_URL")
        if not url:
            raise RuntimeError(
                "APP_DATABASE_URL is not set. Add your Neon connection string "
                "(postgresql://USER:PASSWORD@HOST/DB?sslmode=require) to .env."
            )
        _engine = create_engine(url, echo=False, pool_pre_ping=True)
    return _engine


def init_db() -> None:
    """Create the history tables if they don't exist (idempotent)."""
    # import models so their tables register before create
    from models import ChatSession, TraceLog, User  # noqa: F401
    from sqlalchemy.orm import configure_mappers

    # validate relationships at startup, not on first query
    configure_mappers()
    SQLModel.metadata.create_all(get_engine())
    logger.info("Postgres history schema ready.")


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a session, closed afterwards."""
    with Session(get_engine()) as session:
        yield session
