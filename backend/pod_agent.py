"""Pod agent — the REALITY-side control loop that runs on each serving pod.

It periodically asks the Control Plane "what should I be serving?" (its
PodAssignment rows joined to Organization) and, whenever an org's
``desired_artifact_id`` (INTENT, set by the worker) differs from what this pod has
loaded, it performs the handshake:

    1. download the desired artifact from its s3_uri  (mock: local copy)
    2. atomic swap: point the in-memory TenantDatabaseRegistry at the new file
    3. write ``pod_assignment.loaded_artifact_id = desired`` (REALITY caught up)

The gateway routes on ``load_status='ready'``; the worker never touches routing.
Because the pod only advances REALITY after a fully-local, verified swap, a crash
mid-download leaves desired != loaded and simply retries next tick — self-healing.

Run modes:
  * embedded: api.py starts ``run_pod_agent`` as an asyncio task (env-gated).
  * standalone: ``python pod_agent.py`` for a dedicated agent process.
"""

import asyncio
import logging
import os

from sqlmodel import Session, select

import storage
from models.control_plane import (
    ArtifactStatus,
    GraphArtifact,
    LoadStatus,
    Organization,
    PodAssignment,
    get_control_plane_engine,
)
from registry import REGISTRY, TenantDatabaseRegistry
from tracerag import config
from worker.tasks import _utcnow  # shared UTC helper

logger = logging.getLogger("tracerag.pod_agent")

POD_ID = config.POD_ID
POLL_INTERVAL = float(os.getenv("POD_AGENT_POLL_INTERVAL", "5"))

# The pod's live view of what it serves — the SAME registry the API routers and
# MCP provider read, so a swap here is immediately visible to request handling.
registry = REGISTRY


def reconcile_assignments(
    engine=None, *, pod_id: str = POD_ID, reg: TenantDatabaseRegistry | None = None
) -> list[dict]:
    """One reconcile pass: bring every assigned org's REALITY up to its INTENT.
    Returns a summary of the swaps performed this pass (empty when already caught up)."""
    engine = engine or get_control_plane_engine()
    reg = reg or registry
    changes: list[dict] = []

    with Session(engine) as db:
        rows = db.exec(
            select(PodAssignment, Organization)
            .join(Organization, PodAssignment.org_id == Organization.org_id)
            .where(PodAssignment.pod_id == pod_id)
        ).all()

        for assignment, org in rows:
            desired = org.desired_artifact_id
            loaded = assignment.loaded_artifact_id
            if not desired or desired == loaded:
                continue  # nothing published yet, or REALITY already matches INTENT

            artifact = db.get(GraphArtifact, desired)
            if artifact is None or artifact.status not in (
                ArtifactStatus.READY, ArtifactStatus.ACTIVE
            ):
                logger.warning("pod=%s org=%s desired=%s not registered/ready; skip",
                               pod_id, org.org_id, desired)
                continue

            # 1) download (mock copy) to this pod's local cache
            dest = storage.pod_artifact_path(pod_id, org.org_id, artifact.version)
            storage.get_artifact(artifact.s3_uri, dest)
            # 2) verify integrity before swapping in
            if artifact.checksum_sha256 and storage.sha256_file(dest) != artifact.checksum_sha256:
                logger.error("pod=%s org=%s checksum mismatch for %s; not swapping",
                             pod_id, org.org_id, desired)
                continue
            # 3) atomic swap: REALITY now points at the new file
            reg.swap(org.org_id, artifact.artifact_id, artifact.version, dest)

            # 4) record REALITY in the control plane (only the pod writes this)
            assignment.loaded_artifact_id = desired
            assignment.load_status = LoadStatus.READY
            assignment.last_confirmed_at = _utcnow()
            db.add(assignment)
            # first time this version is served, promote it to ACTIVE
            if artifact.status != ArtifactStatus.ACTIVE:
                artifact.status = ArtifactStatus.ACTIVE
                db.add(artifact)
            db.commit()

            logger.info("pod=%s SWAP org=%s %s -> %s (v%d)",
                        pod_id, org.org_id, loaded, desired, artifact.version)
            changes.append({
                "org_id": org.org_id, "from": loaded, "to": desired,
                "version": artifact.version,
            })

    return changes


async def run_pod_agent(
    stop_event: asyncio.Event, *, pod_id: str = POD_ID, interval: float = POLL_INTERVAL
) -> None:
    """Poll the Control Plane forever (until stop_event), reconciling each tick.
    Blocking DB/IO runs off the event loop so it never stalls the API."""
    logger.info("pod agent started (pod_id=%s, interval=%ss)", pod_id, interval)
    while not stop_event.is_set():
        try:
            await asyncio.to_thread(reconcile_assignments, pod_id=pod_id)
        except Exception:  # noqa: BLE001 — one bad tick must not kill the loop
            logger.exception("pod agent tick failed (pod=%s)", pod_id)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass  # normal: interval elapsed, poll again
    logger.info("pod agent stopped (pod_id=%s)", pod_id)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    _stop = asyncio.Event()
    try:
        asyncio.run(run_pod_agent(_stop))
    except KeyboardInterrupt:
        pass
