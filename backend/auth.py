"""Clerk session-token verification for FastAPI (networkless JWT verification).

Clerk issues short-lived RS256 JWTs. RS256 is *asymmetric*: Clerk signs with a
private key it never shares, and publishes the matching PUBLIC key at a JWKS
(JSON Web Key Set) endpoint. We fetch those public keys once, cache them, and
verify each incoming token's signature locally — no network round-trip per
request. If the signature + claims check out, the token's `sub` claim is a
Clerk user id we can trust (it could not have been forged without Clerk's
private key).

Dev escape hatch: when CLERK_ISSUER is unset we skip verification entirely and
return a fixed dev user id, so local development without Clerk env vars is never
locked out. Configured => enforce; unconfigured => warn-and-allow.
"""

from __future__ import annotations

import logging

import jwt
from fastapi import Header, HTTPException, Request, status
from jwt import PyJWKClient, PyJWKClientError

from tracerag import config

logger = logging.getLogger("tracerag.auth")

# PyJWKClient fetches the JWKS once and caches the signing keys in-process,
# only re-fetching when it sees a token signed by an unknown `kid` (key id) —
# which is exactly how it transparently handles Clerk rotating its keys.
# Built lazily as a singleton so we don't hit the network at import time.
_jwk_client: PyJWKClient | None = None
_warned_dev_bypass = False


def _get_jwk_client() -> PyJWKClient:
    global _jwk_client
    if _jwk_client is None:
        _jwk_client = PyJWKClient(config.CLERK_JWKS_URL, cache_keys=True)
    return _jwk_client


def _extract_bearer(authorization: str | None) -> str:
    """Pull the raw JWT out of an `Authorization: Bearer <token>` header."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # partition splits on the FIRST space: "Bearer" | " " | "<token>"
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header must be 'Bearer <token>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


def _verify_token(token: str) -> dict:
    """Verify the signature and the standard claims; return the decoded payload.

    Two distinct failure classes, surfaced differently:
      - we couldn't resolve a signing key (JWKS unreachable / unknown kid)
      - the token itself is bad (expired, wrong issuer, tampered signature)
    """
    # --- Step 1: find the PUBLIC key that matches this token's `kid` header. ---
    # PyJWKClient reads the unverified header (just the kid, not the payload) and
    # hands back the corresponding public key from Clerk's JWKS.
    try:
        signing_key = _get_jwk_client().get_signing_key_from_jwt(token)
    except PyJWKClientError as exc:
        # Couldn't fetch/match a key — a server/config problem, not a forged
        # token. Log loudly; still answer 401 so we never leak internals.
        logger.warning("JWKS key resolution failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not resolve token signing key.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.DecodeError as exc:
        # Header itself was malformed (not a real JWT).
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Malformed token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # --- Step 2: verify signature AND the registered claims in one call. ---
    # jwt.decode() does ALL of the following atomically and raises if any fails:
    #   * RS256 signature matches `signing_key`        -> token is authentic
    #   * `exp` (expiry) is in the future              -> token still valid
    #   * `nbf`/`iat` not in the future (with leeway)  -> token already active
    #   * `iss` equals our Clerk instance              -> minted by OUR Clerk
    #   * the `require` claims are all present          -> well-formed session
    try:
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],          # PIN the algorithm — never accept
                                           # 'none'/HS256, which would let an
                                           # attacker self-sign a token.
            issuer=config.CLERK_ISSUER,    # `iss` must equal our Clerk instance.
            leeway=5,                      # tolerate ≤5s of clock skew on exp/nbf.
            options={
                "require": ["exp", "iat", "sub"],  # must be present or reject.
                "verify_aud": False,       # Clerk session tokens carry no `aud`;
                                           # we authorize via `azp` below instead.
            },
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as exc:
        # Catch-all for bad signature, wrong issuer, missing required claim, etc.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # --- Step 3: optional `azp` (authorized party) check. ---
    # `azp` is the origin the token was minted for. Verifying it against an
    # allow-list stops a token issued for some other site from being replayed
    # against our API. Skipped entirely if CLERK_AUTHORIZED_PARTIES is unset.
    if config.CLERK_AUTHORIZED_PARTIES:
        azp = claims.get("azp")
        if azp and azp not in config.CLERK_AUTHORIZED_PARTIES:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token authorized-party (azp) is not allowed.",
                headers={"WWW-Authenticate": "Bearer"},
            )
    return claims


def get_current_user(
    request: Request,
    authorization: str | None = Header(default=None),
) -> str:
    """FastAPI dependency → the verified Clerk user id (`sub`).

    Add `user_id: str = Depends(get_current_user)` to any route to (a) require a
    valid token and (b) receive the trustworthy user id. Routes should rely on
    THIS value, never on a client-supplied user_id — that's what closes IDOR.

    Side effect: stashes the resolved id on `request.state.user_id`. This is the
    bridge that lets slowapi's key_func rate-limit per USER — the key_func only
    receives the Request, not this dependency's return value, but FastAPI
    resolves dependencies BEFORE the rate-limit decorator runs, so by then
    request.state.user_id is populated. See ratelimit.py.
    """
    user_id = _resolve_user_id(authorization)
    request.state.user_id = user_id
    return user_id


def _resolve_user_id(authorization: str | None) -> str:
    """Verify the token (or dev-bypass) and return the user id."""
    # Dev-bypass: no Clerk configured → don't verify, return a fixed dev user so
    # local testing isn't blocked. Warn once so it can't silently ship to prod.
    if not config.CLERK_ENABLED:
        global _warned_dev_bypass
        if not _warned_dev_bypass:
            logger.warning(
                "CLERK_ISSUER unset — auth is in DEV-BYPASS mode; every request "
                "runs as '%s'. Do NOT deploy without setting CLERK_ISSUER.",
                config.DEV_USER_ID,
            )
            _warned_dev_bypass = True
        return config.DEV_USER_ID

    token = _extract_bearer(authorization)
    claims = _verify_token(token)
    return claims["sub"]  # the Clerk user id — safe to trust post-verification.
