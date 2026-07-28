"""Age-based score decay: score *= 0.5 ** (age_days / half_life), floored.

A true half-life — at exactly half_life days the multiplier is 0.5 — so the
config numbers mean what they say when you tune them.

Half-life is per entity type — an incident goes stale in weeks, a service
definition in a year. Items with no timestamp are left untouched rather than
penalised, so a graph without dates behaves exactly as it did before.
"""

from __future__ import annotations

import time

from . import config

SECONDS_PER_DAY = 86400.0


def age_days(ts: int | None, now: float | None = None) -> float | None:
    """Age in days, or None when the item carries no usable timestamp."""
    if not ts:
        return None
    now = time.time() if now is None else now
    return max(0.0, (now - float(ts)) / SECONDS_PER_DAY)


def half_life_for(node_type: str | None) -> float:
    return config.RECENCY_HALF_LIFE_DAYS.get(
        node_type or "", config.DEFAULT_HALF_LIFE_DAYS
    )


def decay_factor(
    ts: int | None, node_type: str | None = None, now: float | None = None
) -> float:
    """Multiplier in [RECENCY_FLOOR, 1.0]. 1.0 when recency is off or ts is unknown."""
    if not config.RECENCY_ENABLED:
        return 1.0
    age = age_days(ts, now)
    if age is None:
        return 1.0
    factor = 0.5 ** (age / half_life_for(node_type))
    return max(config.RECENCY_FLOOR, factor)
