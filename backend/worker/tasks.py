"""Celery tasks for the reconcile-to-HEAD pipeline.

Two tasks + one webhook entry point:

  request_reconcile(org_id)        — call this from the GitHub webhook handler.
                                      Only arms the Redis debounce; no compile.
  sweep_due_reconciliations()      — Beat-scheduled. Claims orgs whose debounce
                                      window closed and enqueues one reconcile each.
  reconcile_org_to_head(org_id)    — THE compile. Reconciles ALL of an org's repos
                                      to HEAD, compiles a fresh .lbug, registers it,
                                      and flips the org's desired pointer.

Everything below the phase comments in reconcile_org_to_head is scaffolding: the
control-plane writes and status transitions are real, the heavy engine calls
(fetch / GLiNER / compile / S3) are TODO stubs to fill in next.
"""

import logging
import time
from contextlib import contextmanager
from datetime import datetime, timezone

from pathlib import Path

from sqlmodel import Session, select

import storage
from models.control_plane import (
    ArtifactStatus,
    GraphArtifact,
    IngestJob,
    JobStatus,
    Organization,
    Repository,
    get_control_plane_engine,
)
from worker import debounce, settings
from worker.celery_app import app

logger = logging.getLogger("tracerag.worker")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Webhook entry point — the ONLY thing the API calls on a PR merge.
# ---------------------------------------------------------------------------
def request_reconcile(org_id: str) -> float:
    """Arm the debounce window for an org. Cheap and idempotent — a burst of
    webhooks collapses into a single compile when the window closes. Returns the
    effective deadline (unix seconds)."""
    deadline = debounce.arm(org_id)
    logger.info("reconcile armed for org=%s (fires ~%.0fs)", org_id,
                max(0.0, deadline - time.time()))
    return deadline


# ---------------------------------------------------------------------------
# Beat-scheduled sweeper — turns closed windows into enqueued reconciles.
# ---------------------------------------------------------------------------
@app.task(name="worker.tasks.sweep_due_reconciliations")
def sweep_due_reconciliations() -> int:
    """Claim every org whose debounce window has closed and enqueue its reconcile.
    Returns the number dispatched (0 on a quiet tick)."""
    due = debounce.claim_due()
    for org_id in due:
        reconcile_org_to_head.delay(org_id)
    if due:
        logger.info("sweeper dispatched %d reconcile(s): %s", len(due), due)
    return len(due)


# ---------------------------------------------------------------------------
# Per-org compile lock — serialize compiles for ONE org without serializing the
# cheap incremental-compute step. If a second reconcile fires while one holds the
# lock, it skips; the org's next armed window re-fires it, so no delta is lost.
# ---------------------------------------------------------------------------
@contextmanager
def _org_compile_lock(org_id: str):
    r = debounce.get_client()
    key = f"reconcile:lock:{org_id}"
    token = str(time.time())
    acquired = r.set(key, token, nx=True, ex=settings.COMPILE_LOCK_TTL)
    try:
        yield bool(acquired)
    finally:
        if acquired:
            # only release if we still own it (avoid clobbering a lock that
            # expired and was re-acquired by another worker).
            if r.get(key) == token:
                r.delete(key)


# ---------------------------------------------------------------------------
# THE compile. Reconcile every repo in the org to HEAD, compile a fresh artifact,
# register it, flip the desired pointer. Idempotent: re-running just reconciles to
# HEAD again. The Celery task wraps the per-org lock; the core is a plain function
# so it can be driven directly (tests / manual runs) without a broker.
# ---------------------------------------------------------------------------
@app.task(name="worker.tasks.reconcile_org_to_head", bind=True, max_retries=5)
def reconcile_org_to_head(self, org_id: str) -> dict:
    from worker.ingestion.github_client import GitHubRateLimitError

    engine = get_control_plane_engine()
    with _org_compile_lock(org_id) as got_lock:
        if not got_lock:
            # another compile for this org is in flight — coalesce, don't race.
            logger.info("org=%s compile already running; skipping (will re-fire).",
                        org_id)
            return {"org_id": org_id, "status": "skipped_locked"}
        try:
            return _reconcile_core(org_id, engine)
        except GitHubRateLimitError as exc:
            # transient: back off until the limit resets and retry (the failed job
            # row frees the partial-unique slot, so the retry opens a fresh one).
            countdown = min(exc.retry_after or 60, 3600)
            logger.warning("org=%s rate-limited; retrying in %ss", org_id, countdown)
            raise self.retry(exc=exc, countdown=countdown)


def _reconcile_core(org_id: str, engine) -> dict:
    # ---- open a job (DB half of debounce: the partial unique index caps this
    # at one in-flight job per org; a racing insert would raise -> coalesce) ----
    with Session(engine) as db:
        org = db.get(Organization, org_id)
        if org is None:
            logger.warning("reconcile: unknown org_id=%s", org_id)
            return {"org_id": org_id, "status": "unknown_org"}
        job = IngestJob(org_id=org_id, trigger="schedule",
                        status=JobStatus.FETCHING, started_at=_utcnow())
        db.add(job)
        db.commit()
        db.refresh(job)
        job_id = job.job_id
    logger.info("reconcile start org=%s job=%s", org_id, job_id)
    try:
        return _run_phases(engine, org_id, job_id)
    except Exception as exc:  # noqa: BLE001 — surface the failure on the job row
        logger.exception("reconcile failed org=%s job=%s", org_id, job_id)
        _finalize_job(engine, job_id, status=JobStatus.FAILED, error=str(exc))
        raise


def _run_phases(engine, org_id: str, job_id: str) -> dict:
    # -- Phase 1 FETCH + Phase 2 COMPUTE (incremental, REAL) --------------------
    # For each repo, pull only the delta since its cursor, run the NLP extractor,
    # and UPSERT nodes/edges/embeddings into the durable graph store. entity_count
    # is now the real node count for the org, not a mock.
    from models.graph_store import get_graph_store_engine
    from worker.ingestion.pipeline import run_incremental_ingest

    _set_status(engine, job_id, JobStatus.COMPUTING)
    gs_engine = get_graph_store_engine()
    with Session(engine) as db:
        # decrypt each repo's token here, worker-side, only when about to fetch.
        repo_list = [
            (r.repo_id, r.name, r.last_synced_cursor, r.get_github_token())
            for r in db.exec(select(Repository).where(Repository.org_id == org_id)).all()
        ]
    new_cursors: dict[str, str] = {}
    for repo_id, name, cursor, token in repo_list:
        res = run_incremental_ingest(org_id, repo_id, name, cursor, gs_engine,
                                     github_token=token)
        if res["new_cursor"]:
            new_cursors[repo_id] = res["new_cursor"]
    version = _next_version(engine, org_id)

    # -- Phase 3 COMPILE (REAL): read the org's durable graph from Postgres and
    #    build the optimized .lbug — including the CPU-heavy HNSW index, which we
    #    deliberately run here on the worker, never on the serving pods. -----------
    _set_status(engine, job_id, JobStatus.COMPILING)
    from worker.ingestion.compiler import compile_graph_for_org

    out_path = storage.build_dir(org_id) / f"v{version}.lbug"
    compiled = compile_graph_for_org(org_id, gs_engine, out_path)
    local_path = Path(compiled["path"])
    entity_count = compiled["entity_count"]   # authoritative: what's in the artifact
    checksum = storage.sha256_file(local_path)
    size_bytes = local_path.stat().st_size

    # -- Phase 4a UPLOAD ---------------------------------------------------------
    _set_status(engine, job_id, JobStatus.UPLOADING)
    key = storage.artifact_key(org_id, version)
    s3_uri = storage.put_artifact(local_path, key)

    # -- Phase 4b REGISTER + POINTER FLIP (one atomic transaction) --------------
    # Insert the artifact (READY), supersede the prior published one, flip the
    # org's INTENT pointer, complete the job, and bump repo cursors — all or
    # nothing, so a pod never sees a desired pointer to an unregistered artifact.
    with Session(engine) as db:
        artifact = GraphArtifact(
            org_id=org_id, version=version, s3_uri=s3_uri,
            checksum_sha256=checksum, size_bytes=size_bytes,
            entity_count=entity_count, status=ArtifactStatus.READY,
            built_by_job_id=job_id,
        )
        db.add(artifact)
        db.flush()  # assigns artifact.artifact_id
        artifact_id = artifact.artifact_id

        org = db.get(Organization, org_id)
        prior_id = org.desired_artifact_id
        if prior_id:
            prior = db.get(GraphArtifact, prior_id)
            if prior and prior.status in (ArtifactStatus.READY, ArtifactStatus.ACTIVE):
                prior.status = ArtifactStatus.SUPERSEDED
                db.add(prior)
        org.desired_artifact_id = artifact_id        # <- the INTENT flip
        org.updated_at = _utcnow()
        db.add(org)

        job = db.get(IngestJob, job_id)
        job.status = JobStatus.COMPLETED
        job.produced_artifact_id = artifact_id
        job.cursor_to = max(new_cursors.values()) if new_cursors else None
        job.finished_at = _utcnow()
        db.add(job)

        # Phase 5: advance each repo's sync cursor to the point we ingested up to.
        for repo in db.exec(select(Repository).where(Repository.org_id == org_id)).all():
            if new_cursors.get(repo.repo_id):
                repo.last_synced_cursor = new_cursors[repo.repo_id]
            repo.last_synced_at = _utcnow()
            db.add(repo)

        db.commit()

    logger.info("reconcile done org=%s job=%s -> artifact=%s v%d (desired flipped)",
                org_id, job_id, artifact_id, version)
    return {"org_id": org_id, "job_id": job_id, "artifact_id": artifact_id,
            "version": version, "s3_uri": s3_uri, "status": "completed"}


# ---------------------------------------------------------------------------
# Small control-plane helpers used by the phases above.
# ---------------------------------------------------------------------------
def _set_status(engine, job_id: str, status: str) -> None:
    with Session(engine) as db:
        job = db.get(IngestJob, job_id)
        if job:
            job.status = status
            db.add(job)
            db.commit()


def _finalize_job(engine, job_id: str, *, status: str, error: str | None = None) -> None:
    with Session(engine) as db:
        job = db.get(IngestJob, job_id)
        if job:
            job.status = status
            job.error = error
            job.finished_at = _utcnow()
            db.add(job)
            db.commit()


def _next_version(engine, org_id: str) -> int:
    """Next monotonic artifact version for an org (max(existing) + 1)."""
    with Session(engine) as db:
        versions = db.exec(
            select(GraphArtifact.version).where(GraphArtifact.org_id == org_id)
        ).all()
        return (max(versions) + 1) if versions else 1
