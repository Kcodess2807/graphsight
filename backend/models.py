"""SQLModel tables for the Postgres history store (users, sessions, traces)."""

# no `from __future__ import annotations`: it breaks SQLModel relationship targets

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Column, JSON
from sqlmodel import Field, Relationship, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid4())


class User(SQLModel, table=True):
    # Clerk user id from the frontend, not auto-generated
    id: str = Field(primary_key=True)
    email: str = Field(unique=True, index=True)
    created_at: datetime = Field(default_factory=_utcnow)

    sessions: list["ChatSession"] = Relationship(back_populates="user")


class ChatSession(SQLModel, table=True):
    id: str = Field(default_factory=_new_id, primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    title: str = Field(default="New Chat")
    created_at: datetime = Field(default_factory=_utcnow)

    user: User | None = Relationship(back_populates="sessions")
    traces: list["TraceLog"] = Relationship(back_populates="session")


class TraceLog(SQLModel, table=True):
    id: str = Field(default_factory=_new_id, primary_key=True)
    session_id: str = Field(foreign_key="chatsession.id", index=True)
    query: str
    execution_plan: dict = Field(default_factory=dict, sa_column=Column(JSON))
    graph_payload: dict | list = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utcnow)

    session: ChatSession | None = Relationship(back_populates="traces")
