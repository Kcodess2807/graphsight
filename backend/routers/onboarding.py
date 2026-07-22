"""Admin onboarding — provision a whole tenant in one call.

POST /api/admin/onboarding/provision creates the full control-plane state for a
new tenant (Organization + ApiKey + Repository + PodAssignment) in a single
transaction, then arms the first ingestion via the Redis debounce queue. Guarded
by an X-Admin-Secret header so it can never be hit publicly.

The generated API key's RAW value is returned exactly once (only its hash is
stored) — the caller must save it.
"""

import hmac
import logging
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session

import auth
from models.control_plane import (
    ApiKey, LoadStatus, Organization, PodAssignment, Repository,
    get_control_plane_engine,
)
from scheduler.placement import determine_optimal_pod
from tracerag import config

logger = logging.getLogger("tracerag.onboarding")

router = APIRouter(prefix="/api/admin/onboarding", tags=["admin"])


def require_admin(x_admin_secret: str | None = Header(default=None)) -> None:
    """Gate the router on a shared server-side secret (constant-time compare)."""
    expected = config.ADMIN_SECRET_KEY
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Onboarding disabled: ADMIN_SECRET_KEY is not configured.",
        )
    if not x_admin_secret or not hmac.compare_digest(x_admin_secret, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Admin-Secret.",
        )


class ProvisionRequest(BaseModel):
    tenant_name: str
    repo_name: str                       # e.g. "tiangolo/fastapi"
    github_token: str | None = None      # optional per-tenant PAT


class ProvisionResponse(BaseModel):
    org_id: str
    api_key: str                         # RAW — shown once, save it
    pod_id: str
    repository_id: str
    reconcile_armed: bool
    warning: str


def _new_api_key() -> str:
    """A secure, opaque key. Only its SHA-256 is stored; this raw value is the
    one and only copy the caller ever receives."""
    return f"sk_live_{secrets.token_urlsafe(32)}"


@router.post("/provision", response_model=ProvisionResponse,
             dependencies=[Depends(require_admin)])
def provision_tenant(req: ProvisionRequest) -> ProvisionResponse:
    org_id = f"org_{secrets.token_hex(8)}"
    raw_key = _new_api_key()

    engine = get_control_plane_engine()
    # single transaction: everything commits together or not at all.
    with Session(engine) as db:
        # elastic placement: least-loaded healthy pod (falls back to local pod).
        pod_id = determine_optimal_pod(db)

        db.add(Organization(org_id=org_id, name=req.tenant_name))

        db.add(ApiKey(
            org_id=org_id,
            hashed_key=auth.hash_api_key(raw_key),   # store only the hash
            prefix=raw_key[:12],                     # display-only fingerprint
            scopes="read",
        ))

        repo = Repository(
            org_id=org_id,
            provider="github",
            external_id=req.repo_name,               # "owner/repo" as the stable id
            name=req.repo_name,
            last_synced_cursor=None,                 # first sync pulls from scratch
        )
        repo.set_github_token(req.github_token)      # encrypted at rest (or None)
        db.add(repo)
        db.flush()                                   # assigns repo.repo_id
        repository_id = repo.repo_id

        db.add(PodAssignment(
            pod_id=pod_id, org_id=org_id,
            load_status=LoadStatus.PULLING,          # nothing loaded here yet
        ))

        db.commit()

    logger.info("provisioned tenant org=%s repo=%s -> pod=%s",
                org_id, req.repo_name, pod_id)

    # prime the first ingestion (arms the Redis debounce; sweeper fires it soon).
    reconcile_armed = True
    try:
        from worker.tasks import request_reconcile

        request_reconcile(org_id)
    except Exception as exc:  # noqa: BLE001 — provisioning already succeeded
        reconcile_armed = False
        logger.warning("could not arm reconcile for %s: %s", org_id, exc)

    return ProvisionResponse(
        org_id=org_id,
        api_key=raw_key,
        pod_id=pod_id,
        repository_id=repository_id,
        reconcile_armed=reconcile_armed,
        warning="Save this api_key now — it is shown only once and cannot be recovered.",
    )
