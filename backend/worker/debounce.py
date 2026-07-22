"""Debounce-and-coalesce for per-org reconciles, backed by Redis.

Design: a single sorted set ``reconcile:due`` maps org_id -> *effective deadline*
= min(now + WINDOW, first_seen + MAX_WAIT). Every webhook re-arms the org (slides
the deadline), and a burst collapses into one entry. The Beat sweeper claims all
members scored at or below `now` in one atomic Lua pop, so two sweepers can never
double-fire the same org.

The API webhook only ever calls ``arm(org_id)`` (cheap, no Celery). The sweeper
calls ``claim_due()``. Nothing here compiles — it just decides *when* to enqueue.
"""

import time

import redis

from worker import settings

# ZSET of armed orgs, scored by effective deadline (unix seconds).
_DUE_ZSET = "reconcile:due"
# HASH org_id -> first-armed timestamp, for the MAX_WAIT cap.
_FIRST_HASH = "reconcile:first"

_client = None

# Atomically pop every member scored <= now: read the due members, then remove
# them from BOTH the ZSET and the first-seen HASH in one server-side step.
_CLAIM_LUA = """
local due = redis.call('ZRANGEBYSCORE', KEYS[1], '-inf', ARGV[1])
if #due > 0 then
  redis.call('ZREM', KEYS[1], unpack(due))
  redis.call('HDEL', KEYS[2], unpack(due))
end
return due
"""


def get_client() -> "redis.Redis":
    """Process-wide Redis client (decoded responses), created on first use."""
    global _client
    if _client is None:
        _client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _client


def arm(org_id: str, now: float | None = None) -> float:
    """Arm/extend the debounce window for an org. Returns the effective deadline.

    Sliding: each call pushes the deadline to now + WINDOW, but never past
    first_seen + MAX_WAIT — so a hot org still compiles within the cap.
    """
    r = get_client()
    now = time.time() if now is None else now

    # record (once) when this org was first armed in the current window
    if r.hsetnx(_FIRST_HASH, org_id, now):
        first = now
    else:
        first = float(r.hget(_FIRST_HASH, org_id))

    deadline = min(now + settings.DEBOUNCE_WINDOW, first + settings.DEBOUNCE_MAX_WAIT)
    r.zadd(_DUE_ZSET, {org_id: deadline})
    return deadline


def claim_due(now: float | None = None) -> list[str]:
    """Atomically remove and return every org whose window has closed.

    Race-free across concurrent sweepers: the Lua script does the read+remove in
    one step, so each due org is handed to exactly one caller.
    """
    r = get_client()
    now = time.time() if now is None else now
    claim = r.register_script(_CLAIM_LUA)
    return list(claim(keys=[_DUE_ZSET, _FIRST_HASH], args=[now]))


def pending_count() -> int:
    """How many orgs are currently armed (for metrics / debugging)."""
    return int(get_client().zcard(_DUE_ZSET))
