"""Graph-Store schema — the DURABLE TRUTH for tenant graphs.

Separate from the Control Plane (which orchestrates files + fleet). This holds the
actual graph content: entities and relationships, per org, with embeddings. The
``.lbug`` artifacts are COMPILED from these tables; if one is lost, recompile from
here. Own engine (GRAPH_STORE_DATABASE_URL), so it can be split from the control
plane and history stores in production.

Tenant isolation is structural: EntityNode's PRIMARY KEY is the composite
(org_id, node_id), so a node physically cannot exist without an org, the same
node_id can live under two orgs without collision, and every read is org-scoped by
construction — cross-tenant bleed is impossible at the DB level.
"""

# no `from __future__ import annotations`: it breaks SQLModel column typing

import os
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import JSON, Column, Index, UniqueConstraint
from sqlmodel import Field, Session, SQLModel, create_engine, func, select


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid4())


class EntityNode(SQLModel, table=True):
    """A graph entity (a PR, Bug, Person, Service, …) owned by exactly one org."""

    # composite PK => structural tenant isolation + the (org_id, node_id) index.
    org_id: str = Field(primary_key=True, index=True)
    node_id: str = Field(primary_key=True)

    repo_id: Optional[str] = Field(default=None, index=True)
    label: str                                   # entity type: 'PR','Bug','Person',…
    name: str                                    # display/surface form
    properties: dict = Field(default_factory=dict, sa_column=Column(JSON))
    # 384-d MiniLM vector as JSON (portable). Swap to pgvector Vector(384) in prod
    # for ANN in Postgres; the compile step reads these into the .lbug HNSW either way.
    embedding: list = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    __table_args__ = (
        Index("ix_entitynode_org_repo", "org_id", "repo_id"),
        Index("ix_entitynode_org_label", "org_id", "label"),
    )


class EntityEdge(SQLModel, table=True):
    """A directed relationship between two of an org's nodes."""

    edge_id: str = Field(default_factory=_new_id, primary_key=True)
    org_id: str = Field(index=True)
    source_node_id: str
    target_node_id: str
    relation_type: str                            # 'MENTIONS','AUTHORED_BY','FIXES',…
    weight: float = Field(default=1.0)            # confidence
    created_at: datetime = Field(default_factory=_utcnow)

    __table_args__ = (
        # one edge per (org, source, target, relation) — the UPSERT conflict target.
        UniqueConstraint("org_id", "source_node_id", "target_node_id", "relation_type",
                         name="uq_edge_identity"),
        Index("ix_edge_org_source", "org_id", "source_node_id"),
        Index("ix_edge_org_target", "org_id", "target_node_id"),
    )


GRAPH_STORE_MODELS = [EntityNode, EntityEdge]


# =============================================================================
# Engine / schema (own database, separate from control plane + history)
# =============================================================================
_engine = None
_initialized = False


def get_graph_store_engine():
    global _engine
    if _engine is None:
        url = os.getenv("GRAPH_STORE_DATABASE_URL") or os.getenv("APP_DATABASE_URL")
        if not url:
            raise RuntimeError(
                "Set GRAPH_STORE_DATABASE_URL (or APP_DATABASE_URL) to the "
                "graph-store Postgres connection string."
            )
        _engine = create_engine(url, echo=False, pool_pre_ping=True)
    return _engine


def init_graph_store(engine=None) -> None:
    """Create ONLY the graph-store tables (idempotent)."""
    engine = engine or get_graph_store_engine()
    SQLModel.metadata.create_all(
        engine, tables=[m.__table__ for m in GRAPH_STORE_MODELS]
    )


def ensure_graph_store(engine=None) -> None:
    """create_all once per process (cheap guard for the hot ingestion path)."""
    global _initialized
    if not _initialized:
        init_graph_store(engine)
        _initialized = True


# =============================================================================
# Portable UPSERT (Insert … ON CONFLICT DO UPDATE) — works on Postgres and SQLite.
# =============================================================================
def _dialect_insert(engine):
    name = engine.dialect.name
    if name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:  # pragma: no cover
        raise RuntimeError(f"UPSERT unsupported on dialect {name!r}")
    return insert


def upsert_nodes(session: Session, rows: list[dict]) -> int:
    """Insert/refresh entity nodes, keyed on (org_id, node_id). Preserves
    created_at on conflict; refreshes everything else + updated_at."""
    if not rows:
        return 0
    insert = _dialect_insert(session.get_bind())
    now = _utcnow()
    for r in rows:
        r.setdefault("created_at", now)
        r["updated_at"] = now
    stmt = insert(EntityNode.__table__).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["org_id", "node_id"],
        set_={
            "repo_id": stmt.excluded.repo_id,
            "label": stmt.excluded.label,
            "name": stmt.excluded.name,
            "properties": stmt.excluded.properties,
            "embedding": stmt.excluded.embedding,
            "updated_at": stmt.excluded.updated_at,
        },
    )
    session.execute(stmt)
    return len(rows)


def upsert_edges(session: Session, rows: list[dict]) -> int:
    """Insert/refresh edges, keyed on (org_id, source, target, relation)."""
    if not rows:
        return 0
    insert = _dialect_insert(session.get_bind())
    now = _utcnow()
    for r in rows:
        r.setdefault("edge_id", _new_id())
        r.setdefault("created_at", now)
    stmt = insert(EntityEdge.__table__).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["org_id", "source_node_id", "target_node_id", "relation_type"],
        set_={"weight": stmt.excluded.weight},
    )
    session.execute(stmt)
    return len(rows)


def count_nodes_for_org(engine, org_id: str) -> int:
    with Session(engine) as db:
        return int(db.exec(
            select(func.count()).select_from(EntityNode).where(EntityNode.org_id == org_id)
        ).one())


def count_edges_for_org(engine, org_id: str) -> int:
    with Session(engine) as db:
        return int(db.exec(
            select(func.count()).select_from(EntityEdge).where(EntityEdge.org_id == org_id)
        ).one())
