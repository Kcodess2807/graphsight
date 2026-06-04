"""Chat-history endpoints backed by Postgres (Neon) via SQLModel.

    POST /api/sessions                      create or rename a chat session
    GET  /api/sessions?user_id=...          list a user's sessions (newest first)
    GET  /api/sessions/{session_id}/traces  replay a session's trace history

The `/api/trace` endpoint (in api.py) calls ``persist_trace`` to save each
execution; that helper is resilient — a Postgres outage never breaks retrieval.
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from database import get_engine, get_session
from models import ChatSession, TraceLog, User

logger = logging.getLogger("tracerag.history")

router = APIRouter(prefix="/api", tags=["history"])


# --------------------------------------------------------------------------- #
# Request / response schemas
# --------------------------------------------------------------------------- #
class SessionUpsert(BaseModel):
    user_id: str                       # Clerk user id from the frontend
    email: str | None = None           # required only the first time we see a user
    title: str = "New Chat"
    session_id: str | None = None      # set -> rename that session instead of creating


class SessionRead(BaseModel):
    id: str
    user_id: str
    title: str
    created_at: datetime


class TraceRead(BaseModel):
    id: str
    session_id: str
    query: str
    execution_plan: dict
    graph_payload: dict | list
    created_at: datetime


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _ensure_user(db: Session, user_id: str, email: str | None) -> User:
    """Get the user by Clerk id, creating the row on first sight."""
    user = db.get(User, user_id)
    if user is None:
        if not email:
            raise HTTPException(
                status_code=400,
                detail="email is required when first creating a user.",
            )
        user = User(id=user_id, email=email)
        db.add(user)
        db.flush()  # surface unique-email violations before we commit a session
    return user


def persist_trace(
    session_id: str,
    query: str,
    execution_plan: dict,
    graph_payload: dict | list,
) -> str | None:
    """Save one execution to Postgres. Returns the new trace id, or None on any
    failure (missing APP_DATABASE_URL, unknown session_id, DB down) — callers
    treat persistence as best-effort so retrieval is never blocked."""
    try:
        with Session(get_engine()) as db:
            log = TraceLog(
                session_id=session_id,
                query=query,
                execution_plan=execution_plan,
                graph_payload=graph_payload,
            )
            db.add(log)
            db.commit()
            db.refresh(log)
            return log.id
    except Exception as exc:  # noqa: BLE001 — never break /api/trace on a write
        logger.warning("persist_trace failed for session %s: %s", session_id, exc)
        return None


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@router.post("/sessions", response_model=SessionRead)
def create_or_rename_session(
    body: SessionUpsert, db: Session = Depends(get_session)
) -> ChatSession:
    if body.session_id:
        chat = db.get(ChatSession, body.session_id)
        if chat is None:
            raise HTTPException(status_code=404, detail="session not found")
        chat.title = body.title
    else:
        _ensure_user(db, body.user_id, body.email)
        chat = ChatSession(user_id=body.user_id, title=body.title)
        db.add(chat)
    db.commit()
    db.refresh(chat)
    return chat


@router.get("/sessions", response_model=list[SessionRead])
def list_sessions(
    user_id: str = Query(..., description="Clerk user id"),
    db: Session = Depends(get_session),
) -> list[ChatSession]:
    stmt = (
        select(ChatSession)
        .where(ChatSession.user_id == user_id)
        .order_by(ChatSession.created_at.desc())
    )
    return list(db.exec(stmt))


@router.get("/sessions/{session_id}/traces", response_model=list[TraceRead])
def session_traces(
    session_id: str, db: Session = Depends(get_session)
) -> list[TraceLog]:
    if db.get(ChatSession, session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    stmt = (
        select(TraceLog)
        .where(TraceLog.session_id == session_id)
        .order_by(TraceLog.created_at.asc())
    )
    return list(db.exec(stmt))
