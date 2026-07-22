"""GitHub OAuth handshake — connect a tenant's GitHub account so ingestion uses
their token instead of a shared PAT.

  GET /api/github/login?org_id=…   -> 302 to GitHub's authorize page
  GET /api/github/callback         -> exchange code, ENCRYPT the token, store it

The `state` carries the org_id and is HMAC-signed (CSRF + prevents an attacker
binding their token to someone else's org). In production, org_id should come from
the authenticated admin/Clerk session rather than a raw query param.
"""

import hashlib
import hmac
import logging
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Query, status
from sqlmodel import Session, select

from models.control_plane import Repository, get_control_plane_engine
from tracerag import config

logger = logging.getLogger("tracerag.github_oauth")

router = APIRouter(prefix="/api/github", tags=["github-oauth"])

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"


def _require_oauth_config() -> None:
    if not (config.GITHUB_CLIENT_ID and config.GITHUB_CLIENT_SECRET):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "GitHub OAuth is not configured.")


def _sign_state(org_id: str) -> str:
    secret = config.GITHUB_OAUTH_STATE_SECRET
    if not secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "OAuth state secret is not configured.")
    sig = hmac.new(secret.encode(), org_id.encode(), hashlib.sha256).hexdigest()
    return f"{org_id}:{sig}"


def _verify_state(state: str) -> str:
    org_id, _, sig = (state or "").partition(":")
    if not org_id or not sig:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Malformed state.")
    secret = config.GITHUB_OAUTH_STATE_SECRET or ""
    expected = hmac.new(secret.encode(), org_id.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid OAuth state.")
    return org_id


def _exchange_code(code: str, *, transport=None) -> str:
    """Swap an authorization code for an access token. Raises on failure."""
    kwargs = dict(timeout=15.0)
    if transport is not None:
        kwargs["transport"] = transport
    with httpx.Client(**kwargs) as client:
        resp = client.post(
            GITHUB_TOKEN_URL,
            headers={"Accept": "application/json"},
            data={
                "client_id": config.GITHUB_CLIENT_ID,
                "client_secret": config.GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": config.GITHUB_OAUTH_REDIRECT_URI,
            },
        )
    if resp.status_code != 200:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            "GitHub token exchange failed.")
    data = resp.json()
    token = data.get("access_token")
    if not token:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"No access_token from GitHub ({data.get('error', 'unknown')}).")
    return token


@router.get("/login")
def github_login(org_id: str = Query(..., description="tenant to connect")):
    """Redirect the user to GitHub's OAuth authorization page."""
    _require_oauth_config()
    params = urlencode({
        "client_id": config.GITHUB_CLIENT_ID,
        "redirect_uri": config.GITHUB_OAUTH_REDIRECT_URI,
        "scope": config.GITHUB_OAUTH_SCOPES,
        "state": _sign_state(org_id),
        "allow_signup": "false",
    })
    from fastapi.responses import RedirectResponse

    return RedirectResponse(f"{GITHUB_AUTHORIZE_URL}?{params}", status_code=302)


@router.get("/callback")
def github_callback(code: str = Query(...), state: str = Query(...)):
    """Exchange the code, ENCRYPT the token, and store it on the org's repos."""
    _require_oauth_config()
    org_id = _verify_state(state)
    token = _exchange_code(code)

    engine = get_control_plane_engine()
    with Session(engine) as db:
        repos = db.exec(select(Repository).where(Repository.org_id == org_id)).all()
        for repo in repos:
            repo.set_github_token(token)   # encrypted at rest
            db.add(repo)
        db.commit()
        updated = len(repos)

    logger.info("github oauth connected org=%s (%d repos updated)", org_id, updated)
    return {"status": "connected", "org_id": org_id, "repositories_updated": updated}
