"""Per-user rate limiting for the LLM (billed) endpoints, built on slowapi.

slowapi wraps the `limits` library. A limit like "10/minute" is a FIXED-WINDOW
counter by default: one count per (key, 60s window). It's cheap and perfect for
"stop a single user from hammering a paid API", with one caveat — the window
boundary allows a short burst (10 at :59 + 10 at 1:01 = 20 in ~2s). For a smooth
limit with no boundary burst, switch to the moving-window strategy (see below).

The interesting design choice here is the KEY: we rate-limit per authenticated
USER, not per IP. The default slowapi key_func (get_remote_address) keys by IP,
which would make a whole office behind one NAT share a single bucket. Instead our
key_func reads request.state.user_id — which get_current_user populates during
dependency resolution, before this key_func is ever called (see auth.py).
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request


def _user_key(request: Request) -> str:
    """Bucket key = the authenticated user id, falling back to client IP.

    By the time slowapi calls this, FastAPI has already run get_current_user
    (a dependency on the limited routes), so request.state.user_id is set. The
    IP fallback only matters for routes that have no auth dependency — it keeps
    the key_func total so slowapi never crashes on a missing attribute.
    """
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return f"user:{user_id}"
    return f"ip:{get_remote_address(request)}"


# The process-wide limiter.
#
# storage_uri: omitted → defaults to IN-MEMORY storage. That's correct for a
# single uvicorn worker. With --workers N each process keeps its OWN counter, so
# the effective limit becomes N × the configured rate. When you scale to
# multi-worker / multi-instance, point all of them at a shared store:
#
#     limiter = Limiter(
#         key_func=_user_key,
#         storage_uri="redis://localhost:6379",   # shared counter across workers
#         strategy="moving-window",                # smooth limit, no boundary burst
#     )
#
# strategy: omitted → "fixed-window" (the simple counter described above).
limiter = Limiter(key_func=_user_key)

# Single source of truth for the LLM-endpoint rate, applied via @limiter.limit().
LLM_RATE_LIMIT = "10/minute"
