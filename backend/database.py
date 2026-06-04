"""SQLModel engine + session dependency for the external Neon Postgres store.

This Postgres database is SEPARATE from the `.lbug` RAG store: it holds user
sessions, chat history and TraceRAG execution logs (relational metadata), not
vectors or the entity graph. No dual-store-sync concern — the two never overlap.

Reads the connection string from APP_DATABASE_URL (kept distinct from the
LadybugDB path so the two stores are never confused).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

logger = logging.getLogger("tracerag.database")

# Load .env so APP_DATABASE_URL is available even when this module is imported
# before tracerag.config (which also calls load_dotenv). No-op if absent.
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:  # pragma: no cover
    pass

_engine = None  # lazily created so importing this module never needs the URL


def get_engine():
    """Return the process-wide SQLModel engine, creating it on first use.

    ``pool_pre_ping`` is important for serverless Neon: it drops idle
    connections, and pre-ping transparently reconnects instead of erroring.
    """
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
    # Import models so their tables register on SQLModel.metadata before create.
    from models import ChatSession, TraceLog, User  # noqa: F401

    SQLModel.metadata.create_all(get_engine())
    logger.info("Postgres history schema ready.")


def get_session() -> Iterator[Session]:
    """FastAPI dependency: yield a transactional session, closed afterwards."""
    with Session(get_engine()) as session:
        yield session
