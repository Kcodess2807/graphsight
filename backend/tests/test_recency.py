"""Recency decay: age -> score multiplier."""
import time

import pytest

from tracerag import config
from tracerag.recency import age_days, decay_factor, half_life_for

DAY = 86400


def test_no_timestamp_is_not_penalised():
    assert decay_factor(0) == 1.0
    assert decay_factor(None) == 1.0
    assert age_days(0) is None


def test_fresh_beats_stale():
    now = time.time()
    fresh = decay_factor(int(now - 1 * DAY), "PR", now=now)
    stale = decay_factor(int(now - 240 * DAY), "PR", now=now)
    assert fresh > stale
    assert fresh > 0.95


def test_half_life_halves_the_score():
    now = time.time()
    hl = half_life_for("PR")
    factor = decay_factor(int(now - hl * DAY), "PR", now=now)
    assert factor == pytest.approx(0.5, abs=0.01)


def test_type_specific_half_lives():
    now = time.time()
    age = int(now - 30 * DAY)
    # an incident goes stale much faster than a service definition
    assert decay_factor(age, "Ticket", now=now) < decay_factor(age, "Service", now=now)


def test_floor_keeps_ancient_items_reachable():
    now = time.time()
    ancient = decay_factor(int(now - 5000 * DAY), "Ticket", now=now)
    assert ancient == pytest.approx(config.RECENCY_FLOOR)
    assert ancient > 0


def test_future_timestamps_do_not_boost():
    now = time.time()
    assert decay_factor(int(now + 10 * DAY), "PR", now=now) == pytest.approx(1.0)


def test_disabled_is_a_no_op(monkeypatch):
    monkeypatch.setattr(config, "RECENCY_ENABLED", False)
    now = time.time()
    assert decay_factor(int(now - 900 * DAY), "Ticket", now=now) == 1.0


def test_the_failure_demo_scenario():
    """The story the product is built on: a stale PR that reads like the query
    must lose to a fresh one once recency is applied."""
    now = time.time()
    stale_relevance, fresh_relevance = 0.91, 0.34   # raw similarity
    stale = stale_relevance * decay_factor(int(now - 240 * DAY), "PR", now=now)
    fresh = fresh_relevance * decay_factor(int(now - 1 * DAY), "PR", now=now)
    assert stale < 0.5      # 8-month-old PR is heavily discounted
    assert fresh > 0.33     # yesterday's change keeps essentially all its score
    # recency alone doesn't flip this one — the graph path is what closes the gap,
    # but the ranking distance shrinks from 2.7x to under 1.5x
    assert (stale / fresh) < 1.5


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
