"""Control-plane schema: orchestrates the Cell Model, atomic swaps, and the
serving fleet. This Postgres is the *coordination* layer — it tracks files and
pods, never graph content (nodes/edges/embeddings live in the graph-store
Postgres and the compiled ``.lbug`` artifacts).

Seven tables:
  Organization   — the tenant. Holds ``desired_artifact_id`` = the version the
                   compiler last published (INTENT).
  Repository     — repos under an org. ``last_synced_cursor`` drives incremental
                   compute (fetch only cursor->HEAD).
  GraphArtifact  — append-only registry of every compiled ``.lbug`` version in S3.
                   Rollback = repoint the org's desired pointer at an older row.
  IngestJob      — Celery orchestration + audit trail + debounce surface. A
                   partial unique index enforces ONE active job per org.
  Pod            — the serving fleet (fungible, sticky).
  PodAssignment  — sticky org->pod. ``loaded_artifact_id`` = what the pod has
                   actually pulled+swapped to (REALITY). desired != loaded is the
                   transition window; the API gateway routes on this table.
  ApiKey         — per-org keys (MCP / API). Hashed at rest.

Intentionally relationship-light: the worker and gateway query by explicit ids,
so we keep FK columns + indexes and skip ORM relationships (fewer mapper
footguns on the two circular pointer FKs).
"""

# no `from __future__ import annotations`: it breaks SQLModel column typing

import os
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import Column, ForeignKey, Index, String, UniqueConstraint, text
from sqlmodel import Field, SQLModel, create_engine


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid4())


# ---- canonical status vocabularies (stored as plain strings; portable DDL) ----
class ArtifactStatus:
    BUILDING = "building"
    READY = "ready"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    FAILED = "failed"


class JobStatus:
    QUEUED = "queued"
    FETCHING = "fetching"
    COMPUTING = "computing"
    COMPILING = "compiling"
    UPLOADING = "uploading"
    REGISTERED = "registered"
    SWAPPED = "swapped"
    COMPLETED = "completed"   # artifact registered + desired pointer flipped (worker done)
    FAILED = "failed"
    # a job in any of these is "in flight" — the partial unique index below uses
    # this set to enforce one active reconcile per org (debounce/coalesce).
    # COMPLETED/SWAPPED/FAILED are terminal, so a new reconcile may start.
    ACTIVE = (QUEUED, FETCHING, COMPUTING, COMPILING, UPLOADING, REGISTERED)


class PodStatus:
    BOOTING = "booting"
    READY = "ready"
    DRAINING = "draining"
    DEAD = "dead"


class LoadStatus:
    PULLING = "pulling"   # pod is downloading the artifact from S3
    READY = "ready"       # pod has swapped to it and can serve — gateway may route here
    FAILED = "failed"


# =============================================================================
# Tables
# =============================================================================
class Organization(SQLModel, table=True):
    """The tenant (one physical ``.lbug`` cell per org). ``org_id`` is the Clerk
    Organization id, so tenancy lines up with the auth layer."""

    org_id: str = Field(primary_key=True)  # Clerk org_id (external)
    name: str
    plan: str = Field(default="free")
    status: str = Field(default="active")  # active | suspended

    # INTENT pointer: the artifact version the compiler last published for this
    # org. Reality (what a pod actually serves) lives on PodAssignment. FK uses
    # use_alter because Organization<->GraphArtifact reference each other.
    desired_artifact_id: Optional[str] = Field(
        default=None,
        sa_column=Column(
            String,
            ForeignKey("graphartifact.artifact_id", use_alter=True,
                       name="fk_org_desired_artifact"),
            nullable=True, index=True,
        ),
    )

    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class Repository(SQLModel, table=True):
    """A repo under an org. All of an org's repos compile into the SAME ``.lbug``,
    which is what makes cross-repo traversal native."""

    repo_id: str = Field(default_factory=_new_id, primary_key=True)
    org_id: str = Field(foreign_key="organization.org_id", index=True)
    provider: str = Field(default="github")
    external_id: str                      # provider's repo id
    name: str                             # "owner/repo"
    default_branch: str = Field(default="main")

    # ENGINE of incremental compute: fetch only last_synced_cursor -> HEAD.
    last_synced_cursor: Optional[str] = Field(default=None)
    last_synced_at: Optional[datetime] = Field(default=None)
    # per-repo GitHub token, ENCRYPTED AT REST (Fernet ciphertext) — never assign
    # raw; use set_github_token(). Falls back to the worker's GITHUB_TOKEN if None.
    github_token: Optional[str] = Field(default=None)
    status: str = Field(default="active")
    created_at: datetime = Field(default_factory=_utcnow)

    __table_args__ = (
        UniqueConstraint("org_id", "provider", "external_id",
                         name="uq_repo_org_provider_external"),
    )

    # --- secret handling: the column stores ciphertext, plaintext never touches
    # the DB. Vault is imported lazily so the model has no hard crypto dependency.
    def set_github_token(self, plain: Optional[str]) -> None:
        """Encrypt and store (or clear) the repo's GitHub token."""
        if not plain:
            self.github_token = None
            return
        from security.vault import encrypt_token
        self.github_token = encrypt_token(plain)

    def get_github_token(self) -> Optional[str]:
        """Decrypt the stored token on demand (worker-side). None if unset."""
        if not self.github_token:
            return None
        from security.vault import decrypt_token
        return decrypt_token(self.github_token)


class GraphArtifact(SQLModel, table=True):
    """Append-only registry of compiled ``.lbug`` versions in S3. Never mutated;
    a new compile is a new row. ``entity_count`` is what you watch against the
    ~1M-per-org ceiling before a whale needs sharding."""

    artifact_id: str = Field(default_factory=_new_id, primary_key=True)
    org_id: str = Field(foreign_key="organization.org_id", index=True)
    version: int                          # monotonic per org
    s3_uri: str
    checksum_sha256: Optional[str] = Field(default=None)  # pod verifies after pull
    size_bytes: Optional[int] = Field(default=None)
    entity_count: Optional[int] = Field(default=None)
    status: str = Field(default=ArtifactStatus.BUILDING)

    # which job built this (circular with IngestJob.produced_artifact_id).
    built_by_job_id: Optional[str] = Field(
        default=None,
        sa_column=Column(
            String,
            ForeignKey("ingestjob.job_id", use_alter=True,
                       name="fk_artifact_built_by_job"),
            nullable=True, index=True,
        ),
    )
    created_at: datetime = Field(default_factory=_utcnow)

    __table_args__ = (
        UniqueConstraint("org_id", "version", name="uq_artifact_org_version"),
    )


class IngestJob(SQLModel, table=True):
    """A reconcile-to-HEAD run: Celery orchestration + audit trail. The partial
    unique index enforces ONE in-flight job per org, which is the DB-level half of
    debounce-and-coalesce (the Redis timer is the other half)."""

    job_id: str = Field(default_factory=_new_id, primary_key=True)
    org_id: str = Field(foreign_key="organization.org_id", index=True)
    # null repo_id => org-wide reconcile (the normal case: reconcile ALL repos to HEAD)
    repo_id: Optional[str] = Field(default=None, foreign_key="repository.repo_id")
    trigger: str = Field(default="webhook")   # webhook | manual | schedule
    status: str = Field(default=JobStatus.QUEUED, index=True)

    cursor_from: Optional[str] = Field(default=None)
    cursor_to: Optional[str] = Field(default=None)

    # circular with GraphArtifact.built_by_job_id.
    produced_artifact_id: Optional[str] = Field(
        default=None,
        sa_column=Column(
            String,
            ForeignKey("graphartifact.artifact_id", use_alter=True,
                       name="fk_job_produced_artifact"),
            nullable=True, index=True,
        ),
    )
    error: Optional[str] = Field(default=None)
    queued_at: datetime = Field(default_factory=_utcnow)
    started_at: Optional[datetime] = Field(default=None)
    finished_at: Optional[datetime] = Field(default=None)

    __table_args__ = (
        # Postgres partial unique index: at most one non-terminal job per org.
        # A second reconcile for the same org while one is in flight will violate
        # this and must coalesce into the running one instead of racing a compile.
        Index(
            "uq_one_active_job_per_org",
            "org_id",
            unique=True,
            # same partial predicate on both engines (SQLite also supports partial
            # indexes) so terminal jobs — completed/swapped/failed — don't count,
            # and only one in-flight job per org is allowed.
            postgresql_where=text(
                "status IN ('queued','fetching','computing','compiling',"
                "'uploading','registered')"
            ),
            sqlite_where=text(
                "status IN ('queued','fetching','computing','compiling',"
                "'uploading','registered')"
            ),
        ),
    )


class Pod(SQLModel, table=True):
    """A serving instance. Fungible: if it dies, a blank one boots, reads its
    PodAssignment rows, pulls those orgs' latest artifacts from S3, marks Ready."""

    pod_id: str = Field(default_factory=_new_id, primary_key=True)
    ip: str
    status: str = Field(default=PodStatus.BOOTING)  # booting|ready|draining|dead
    mem_budget_mb: Optional[int] = Field(default=None)  # caps org density per pod
    last_heartbeat_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=_utcnow)


class PodAssignment(SQLModel, table=True):
    """Sticky org->pod, and the routing + cutover ground truth. The gateway routes
    ``org_id`` to the pod whose ``load_status='ready'``. ``loaded_artifact_id`` is
    REALITY — only the pod writes it, and only after a fully-verified local swap,
    so ``org.desired_artifact_id != loaded_artifact_id`` is exactly the transition
    window (self-healing: a crashed pod never advances it)."""

    pod_id: str = Field(foreign_key="pod.pod_id", primary_key=True)
    org_id: str = Field(foreign_key="organization.org_id", primary_key=True)

    # not circular — a plain FK is fine here.
    loaded_artifact_id: Optional[str] = Field(
        default=None, foreign_key="graphartifact.artifact_id", index=True
    )
    load_status: str = Field(default=LoadStatus.PULLING)  # pulling|ready|failed
    assigned_at: datetime = Field(default_factory=_utcnow)
    last_confirmed_at: Optional[datetime] = Field(default=None)


class ApiKey(SQLModel, table=True):
    """Per-org API key (MCP / REST). We store only the hash; the gateway hashes a
    presented key, looks it up here, and resolves ``org_id`` (rejecting if
    ``revoked_at`` is set) before routing to the org's pod."""

    key_id: str = Field(default_factory=_new_id, primary_key=True)
    org_id: str = Field(foreign_key="organization.org_id", index=True)
    hashed_key: str = Field(unique=True, index=True)  # sha256(key); never the raw key
    prefix: str                                       # first chars, for display only
    scopes: str = Field(default="read")               # comma-separated
    created_at: datetime = Field(default_factory=_utcnow)
    revoked_at: Optional[datetime] = Field(default=None)


# tables owned by the control plane (used to create ONLY these, in isolation from
# the shared SQLModel metadata that also holds the history tables).
CONTROL_PLANE_MODELS = [
    Organization, Repository, GraphArtifact, IngestJob, Pod, PodAssignment, ApiKey,
]


# =============================================================================
# Engine / schema management — deliberately separate from the history store so
# the control plane can point at its OWN database (CONTROL_PLANE_DATABASE_URL).
# =============================================================================
_engine = None


def get_control_plane_engine():
    """Process-wide engine for the control-plane DB, created on first use.

    Falls back to APP_DATABASE_URL so a single-database dev setup Just Works;
    set CONTROL_PLANE_DATABASE_URL to split it out in production.
    """
    global _engine
    if _engine is None:
        url = os.getenv("CONTROL_PLANE_DATABASE_URL") or os.getenv("APP_DATABASE_URL")
        if not url:
            raise RuntimeError(
                "Set CONTROL_PLANE_DATABASE_URL (or APP_DATABASE_URL) to the "
                "control-plane Postgres connection string."
            )
        _engine = create_engine(url, echo=False, pool_pre_ping=True)
    return _engine


def init_control_plane(engine=None) -> None:
    """Create ONLY the control-plane tables (idempotent). Restricting to these
    tables keeps history-store tables out of the control-plane database even
    though both share SQLModel's global metadata."""
    engine = engine or get_control_plane_engine()
    tables = [m.__table__ for m in CONTROL_PLANE_MODELS]
    SQLModel.metadata.create_all(engine, tables=tables)
