"""Placement policy — pick the pod a new tenant should be assigned to.

Strategy: **least-loaded** (least-connections). Count active PodAssignments per
pod, keep only pods that are registered *and* healthy (status=ready, recent
heartbeat), and return the healthy pod with the fewest tenants (ties broken
deterministically by pod_id).

Defensive by construction: any failure — no pods registered, the fleet query
errors, the DB is unreachable — falls back to this process's own `POD_ID`
(or `pod-global-dev`), so local/dev and a degraded control plane still place
tenants somewhere serviceable rather than 500.
"""

import logging
import os
from datetime import datetime, timedelta, timezone

from sqlmodel import func, select

from models.control_plane import Pod, PodAssignment, PodStatus
from tracerag import config

logger = logging.getLogger("tracerag.placement")

# A pod with a heartbeat older than this is considered unhealthy (skipped).
HEARTBEAT_TTL = int(os.getenv("TRACERAG_POD_HEARTBEAT_TTL", "120"))
_FALLBACK_POD = config.POD_ID or "pod-global-dev"


def _is_fresh(pod: Pod, now: datetime) -> bool:
    """A just-registered pod (no heartbeat yet) counts as fresh; otherwise the
    heartbeat must be within TTL. Any comparison hiccup errs toward 'fresh'."""
    hb = pod.last_heartbeat_at
    if hb is None:
        return True
    try:
        if hb.tzinfo is None:               # sqlite returns naive datetimes
            hb = hb.replace(tzinfo=timezone.utc)
        return (now - hb) <= timedelta(seconds=HEARTBEAT_TTL)
    except Exception:  # noqa: BLE001
        return True


def determine_optimal_pod(db_session) -> str:
    """Return the pod_id for a new tenant. Never raises — falls back to the local
    pod on any failure."""
    try:
        now = datetime.now(timezone.utc)

        pods = db_session.exec(select(Pod).where(Pod.status == PodStatus.READY)).all()
        healthy = [p.pod_id for p in pods if _is_fresh(p, now)]
        if not healthy:
            logger.warning("no healthy pods registered; placing on fallback %s",
                           _FALLBACK_POD)
            return _FALLBACK_POD

        # current load per healthy pod (0 for a fresh, empty pod)
        counts = {pid: 0 for pid in healthy}
        rows = db_session.exec(
            select(PodAssignment.pod_id, func.count())
            .group_by(PodAssignment.pod_id)
        ).all()
        for pid, n in rows:
            if pid in counts:               # ignore assignments to dead/unknown pods
                counts[pid] = int(n)

        # fewest tenants first; pod_id as a stable tie-break
        best = min(counts.items(), key=lambda kv: (kv[1], kv[0]))[0]
        logger.info("placement -> %s (loads=%s)", best, counts)
        return best
    except Exception as exc:  # noqa: BLE001 — fleet tracking must never block onboarding
        logger.warning("placement query failed (%s); fallback %s", exc, _FALLBACK_POD)
        return _FALLBACK_POD
