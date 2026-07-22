"""Chat-history endpoints backed by Postgres via SQLModel."""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from auth import get_current_user
from database import get_engine, get_session
from models import ChatSession, TraceLog, User

logger = logging.getLogger("tracerag.history")

router = APIRouter(prefix="/api", tags=["history"])


class SessionUpsert(BaseModel):
    # user_id is intentionally NOT trusted from the body anymore — the real user
    # id comes from the verified token (get_current_user). Kept optional purely
    # for backward-compat with the existing frontend payload; it is ignored.
    user_id: str | None = None
    email: str | None = None           # required only on first sight of a user
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


def _ensure_user(db: Session, user_id: str, email: str | None) -> User:
    """Get the user by id, creating the row on first sight.

    Email is best-effort, not a hard requirement: dev-bypass has none, and
    Clerk's email can lag the user id on first load — blocking "new chat" on a
    missing email made history silently break. Fall back to a deterministic
    per-user placeholder (unique, so no constraint clash) and use the real
    address whenever the client supplies it.
    """
    user = db.get(User, user_id)
    if user is None:
        placeholder = f"{user_id}@users.tracerag.local"
        candidate = email or placeholder
        # The email column is unique. If this address is already held by a
        # DIFFERENT id (e.g. a real-Clerk row vs. the dev-bypass "dev-user"),
        # claiming it would 500. Fall back to the per-id placeholder, which only
        # this id can ever own.
        clash = db.exec(select(User).where(User.email == candidate)).first()
        if clash is not None and clash.id != user_id:
            candidate = placeholder
        user = User(id=user_id, email=candidate)
        db.add(user)
        db.flush()  # surface any remaining unique violations before committing
    return user


def session_owner(session_id: str) -> str | None:
    """Return the user_id that owns a session, or None if it doesn't exist.

    Opens its own DB session (like persist_trace) so it can be called from the
    /api/trace endpoint, which has no injected `db` dependency. Used to verify
    ownership before persisting a trace into a session — closes the write-side
    IDOR (writing your trace into someone else's session).
    """
    try:
        with Session(get_engine()) as db:
            chat = db.get(ChatSession, session_id)
            return chat.user_id if chat is not None else None
    except Exception as exc:  # noqa: BLE001 — DB hiccup shouldn't 500 the query
        logger.warning("session_owner lookup failed for %s: %s", session_id, exc)
        return None


def persist_trace(
    session_id: str,
    query: str,
    execution_plan: dict,
    graph_payload: dict | list,
) -> str | None:
    """Save one execution to Postgres; returns the new trace id or None on failure."""
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
    except Exception as exc:  # noqa: BLE001
        logger.warning("persist_trace failed for session %s: %s", session_id, exc)
        return None


@router.post("/sessions", response_model=SessionRead)
def create_or_rename_session(
    body: SessionUpsert,
    user_id: str = Depends(get_current_user),  # verified id, NOT body.user_id
    db: Session = Depends(get_session),
) -> ChatSession:
    if body.session_id:
        chat = db.get(ChatSession, body.session_id)
        if chat is None:
            raise HTTPException(status_code=404, detail="session not found")
        # ownership check: you can only rename a session that is yours
        if chat.user_id != user_id:
            raise HTTPException(status_code=403, detail="not your session")
        chat.title = body.title
    else:
        # create the user row (if new) and the session under the TOKEN's user id
        _ensure_user(db, user_id, body.email)
        chat = ChatSession(user_id=user_id, title=body.title)
        db.add(chat)
    db.commit()
    db.refresh(chat)
    return chat


@router.get("/sessions", response_model=list[SessionRead])
def list_sessions(
    user_id: str = Depends(get_current_user),  # scope strictly to the caller
    db: Session = Depends(get_session),
) -> list[ChatSession]:
    # Only ever return the authenticated user's own sessions. A client can no
    # longer pass someone else's id to read their history (closes the IDOR).
    stmt = (
        select(ChatSession)
        .where(ChatSession.user_id == user_id)
        .order_by(ChatSession.created_at.desc())
    )
    return list(db.exec(stmt))


@router.get("/sessions/{session_id}/traces", response_model=list[TraceRead])
def session_traces(
    session_id: str,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> list[TraceLog]:
    chat = db.get(ChatSession, session_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="session not found")
    # ownership check: you can only read traces from a session that is yours
    if chat.user_id != user_id:
        raise HTTPException(status_code=403, detail="not your session")
    stmt = (
        select(TraceLog)
        .where(TraceLog.session_id == session_id)
        .order_by(TraceLog.created_at.asc())
    )
    return list(db.exec(stmt))
