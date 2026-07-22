"""GitHub webhook listener — real-time ingestion triggers.

POST /api/webhooks/github verifies the payload came from GitHub (HMAC-SHA256 over
the RAW body vs X-Hub-Signature-256), then for a merged PR or a push, finds the
org(s) tracking that repo and arms their debounce via request_reconcile. The
arming is backgrounded so we return 200 to GitHub immediately (webhooks must be
fast or GitHub marks the delivery failed).
"""

import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request, status
from sqlmodel import Session, select

from models.control_plane import Repository, get_control_plane_engine
from tracerag import config

logger = logging.getLogger("tracerag.webhooks")

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


def _verify_signature(body: bytes, signature_header: str | None) -> None:
    """Constant-time HMAC-SHA256 check over the raw body. 503 if we have no secret
    to verify against (never accept an unverifiable payload); 401 on mismatch."""
    secret = config.GITHUB_WEBHOOK_SECRET
    if not secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Webhook secret is not configured.")
    if not signature_header or not signature_header.startswith("sha256="):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing signature.")
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature_header):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid signature.")


def _orgs_for_repo(full_name: str) -> list[str]:
    """Every org tracking this "owner/repo" (a public repo may have several)."""
    engine = get_control_plane_engine()
    with Session(engine) as db:
        rows = db.exec(select(Repository).where(Repository.name == full_name)).all()
    return list({r.org_id for r in rows})


def _arm(org_id: str) -> None:
    try:
        from worker.tasks import request_reconcile

        request_reconcile(org_id)
    except Exception as exc:  # noqa: BLE001 — never crash the webhook thread
        logger.warning("failed to arm reconcile for %s: %s", org_id, exc)


@router.post("/github")
async def github_webhook(
    request: Request,
    background: BackgroundTasks,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
) -> dict:
    body = await request.body()          # RAW bytes — required for signature
    _verify_signature(body, x_hub_signature_256)

    if x_github_event == "ping":
        return {"status": "pong"}
    if x_github_event not in ("pull_request", "push"):
        return {"status": "ignored", "event": x_github_event}

    payload = json.loads(body or b"{}")

    # only act on a *merged* PR close (opened/synchronize/unmerged-close are noise)
    if x_github_event == "pull_request":
        if payload.get("action") != "closed":
            return {"status": "ignored", "action": payload.get("action")}
        if not (payload.get("pull_request") or {}).get("merged"):
            return {"status": "ignored", "reason": "pr not merged"}

    full_name = (payload.get("repository") or {}).get("full_name")
    if not full_name:
        return {"status": "ignored", "reason": "no repository in payload"}

    org_ids = _orgs_for_repo(full_name)
    for org_id in org_ids:
        background.add_task(_arm, org_id)   # respond first, arm after

    logger.info("webhook %s for %s -> armed %d org(s)",
                x_github_event, full_name, len(org_ids))
    return {"status": "accepted", "repository": full_name, "orgs": len(org_ids)}
