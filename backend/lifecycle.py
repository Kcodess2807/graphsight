"""Pod lifecycle — self-registration and boot-time state hydration.

Two jobs on boot, so a rescheduled/crashed pod immediately becomes a usable fleet
member without waiting for user traffic:

  register_pod()                 — upsert this pod (status=ready, heartbeat=now) so
                                   the placement policy can see and pick it.
  sync_pod_assignments_on_boot() — for every org already assigned to THIS pod with
                                   load_status='ready', re-download its artifact and
                                   swap it into the in-memory registry, hydrating
                                   local memory to match the control plane.

Everything is defensive and per-org isolated: a bad row or a missing artifact is
logged and skipped, never fatal to boot.
"""

import logging
import os
from datetime import datetime, timezone

from sqlmodel import Session, select

import storage
from models.control_plane import (
    GraphArtifact, LoadStatus, Pod, PodAssignment, PodStatus, get_control_plane_engine,
)
from registry import REGISTRY

logger = logging.getLogger("tracerag.lifecycle")

POD_IP = os.getenv("POD_IP", "127.0.0.1")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def register_pod(pod_id: str, db_session: Session, *, ip: str | None = None) -> None:
    """Upsert this pod as READY with a fresh heartbeat (idempotent across reboots)."""
    pod = db_session.get(Pod, pod_id)
    now = _utcnow()
    if pod is None:
        db_session.add(Pod(pod_id=pod_id, ip=ip or POD_IP,
                           status=PodStatus.READY, last_heartbeat_at=now))
    else:
        pod.status = PodStatus.READY
        pod.last_heartbeat_at = now
        if ip:
            pod.ip = ip
        db_session.add(pod)
    db_session.commit()
    logger.info("registered pod %s (ready)", pod_id)


def sync_pod_assignments_on_boot(
    pod_id: str, db_session: Session, *, reg=None
) -> list[dict]:
    """Hydrate the registry with every org this pod was already serving. Returns a
    summary of what was loaded. Never raises."""
    reg = reg or REGISTRY
    hydrated: list[dict] = []
    try:
        rows = db_session.exec(
            select(PodAssignment).where(
                PodAssignment.pod_id == pod_id,
                PodAssignment.load_status == LoadStatus.READY,
            )
        ).all()
    except Exception as exc:  # noqa: BLE001
        logger.warning("boot: could not read assignments for %s (%s)", pod_id, exc)
        return hydrated

    for a in rows:
        art_id = a.loaded_artifact_id
        if not art_id:
            continue
        try:
            artifact = db_session.get(GraphArtifact, art_id)
            if artifact is None:
                logger.warning("boot: org=%s references missing artifact %s",
                               a.org_id, art_id)
                continue
            dest = storage.pod_artifact_path(pod_id, a.org_id, artifact.version)
            storage.get_artifact(artifact.s3_uri, dest)     # re-download from S3
            reg.swap(a.org_id, artifact.artifact_id, artifact.version, dest)
            hydrated.append({"org_id": a.org_id, "version": artifact.version})
            logger.info("boot: hydrated org=%s v%d on %s",
                        a.org_id, artifact.version, pod_id)
        except Exception as exc:  # noqa: BLE001 — one bad org can't block the pod
            logger.warning("boot: failed to hydrate org=%s (%s)", a.org_id, exc)
            continue
    return hydrated


def boot_pod(pod_id: str, *, reg=None) -> list[dict]:
    """Full boot routine: register self, then hydrate assigned tenants. Opens and
    closes its own control-plane session."""
    engine = get_control_plane_engine()
    with Session(engine) as db:
        try:
            register_pod(pod_id, db)
        except Exception as exc:  # noqa: BLE001
            logger.warning("boot: pod self-registration failed (%s)", exc)
        return sync_pod_assignments_on_boot(pod_id, db, reg=reg)
