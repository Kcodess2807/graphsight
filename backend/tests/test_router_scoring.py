"""Router scoring: relation-weighted traversal + recency decay.

Uses a fake store and a stub embedder so the ranking logic is tested on its
own — no DB driver, no model download.
"""
import time

import pytest

from tracerag import config
from tracerag.router import TraceRouter

DAY = 86400
NOW = time.time()


class FakeDB:
    """Minimal store: vector hits, typed neighbours, no documents."""

    def __init__(self, hits, neighbours):
        self._hits = hits
        self._neighbours = neighbours

    def vector_search(self, embedding, k=10):
        return self._hits[:k]

    def expand_frontier(self, node_ids, k, max_degree):
        return {n: self._neighbours.get(n, [])[:k] for n in node_ids
                if n in self._neighbours}

    def find_nodes_by_label(self, label):
        return []

    def documents_for_entities(self, ids):
        return {}


def make_router(hits, neighbours):
    r = TraceRouter(FakeDB(hits, neighbours))
    r._encode = lambda text: [0.0] * config.EMBED_DIM  # skip the real embedder
    return r


def hit(node_id, sim, ntype="PR", ts=0, label=None):
    return {"id": node_id, "label": label or node_id, "type": ntype,
            "similarity": sim, "ts": ts}


def nbr(node_id, relation, ntype="PR", ts=0):
    return {"id": node_id, "label": node_id, "type": ntype, "ts": ts,
            "relation": relation,
            "confidence": config.RELATION_WEIGHTS[relation]}


def test_structural_hop_outranks_co_occurrence():
    """A node reached through AUTHORED must beat one reached by proximity."""
    router = make_router(
        hits=[hit("seed", 0.9)],
        neighbours={"seed": [nbr("real", config.RELATION_AUTHORED),
                             nbr("noise", config.RELATION_CO_OCCURS)]},
    )
    res = router.route("who owns this?", top_k=10)
    scores = {r.id: r.score_graph for r in res.results}
    assert scores["real"] > scores["noise"]
    # and the gap is the relation weight ratio, not an accident
    assert scores["real"] / scores["noise"] == pytest.approx(
        config.RELATION_WEIGHTS[config.RELATION_AUTHORED]
        / config.RELATION_WEIGHTS[config.RELATION_CO_OCCURS], rel=1e-3
    )


def test_two_hop_structural_beats_one_hop_proximity():
    router = make_router(
        hits=[hit("seed", 0.9)],
        neighbours={
            "seed": [nbr("pr", config.RELATION_AUTHORED),
                     nbr("noise", config.RELATION_CO_OCCURS)],
            "pr": [nbr("issue", config.RELATION_RESOLVES, ntype="Ticket")],
        },
    )
    res = router.route("which issue did that fix?", top_k=10)
    scores = {r.id: r.score_graph for r in res.results}
    assert scores["issue"] > scores["noise"]


def test_graph_scores_are_no_longer_all_one():
    """Regression: with untyped 1.0 edges every reachable node tied at 1.0."""
    router = make_router(
        hits=[hit("seed", 0.9)],
        neighbours={
            "seed": [nbr("a", config.RELATION_AUTHORED),
                     nbr("b", config.RELATION_TOUCHES),
                     nbr("c", config.RELATION_CO_OCCURS)],
        },
    )
    res = router.route("who owns this?", top_k=10)
    graph_only = {r.score_graph for r in res.results if r.id != "seed"}
    assert len(graph_only) > 1, "traversal produced no ranking gradient"


def test_recency_demotes_a_stale_but_similar_hit():
    """The failure-demo scenario, end to end through the router."""
    stale = hit("pr_stale", 0.91, ts=int(NOW - 240 * DAY))
    fresh = hit("pr_fresh", 0.60, ts=int(NOW - 1 * DAY))
    router = make_router(hits=[stale, fresh], neighbours={})
    res = router.route("explain what broke", top_k=10)
    ranked = [r.id for r in res.results]
    assert ranked[0] == "pr_fresh", f"stale hit still won: {ranked}"


def test_undated_nodes_are_not_penalised():
    router = make_router(
        hits=[hit("dated", 0.8, ts=int(NOW - 300 * DAY)), hit("undated", 0.8, ts=0)],
        neighbours={},
    )
    res = router.route("explain the architecture", top_k=10)
    by_id = {r.id: r for r in res.results}
    assert by_id["undated"].recency == 1.0
    assert by_id["undated"].age_days is None
    assert by_id["dated"].recency < 1.0
    assert by_id["undated"].score_total > by_id["dated"].score_total


def test_facts_carry_typed_links_but_not_proximity_guesses():
    """A link the answer model never sees can't change an answer."""
    router = make_router(
        hits=[hit("issue", 0.9, ntype="Ticket", label="Issue #1")],
        neighbours={"issue": [nbr("pr", config.RELATION_RESOLVES),
                              nbr("noise", config.RELATION_CO_OCCURS)],
                    "pr": [nbr("issue", config.RELATION_RESOLVES)]},
    )
    res = router.route("which pr fixed this", top_k=10)
    assert res.facts == ["Issue #1 <-> pr: RESOLVES"]  # one line, though walked both ways
    assert "Issue #1 <-> pr: RESOLVES" in router.build_context(res.results, res.facts)


def test_an_id_in_the_question_seeds_the_walk_without_similarity():
    """'issue #3907' must not depend on how close its embedding happens to be."""
    router = make_router(hits=[], neighbours={"i": [nbr("pr", config.RELATION_RESOLVES)]})
    router.db.find_nodes_by_label = lambda label: (
        [{"id": "i", "label": label, "type": "Ticket"}] if label == "Issue #7" else [])
    router._get_extractor = lambda: type("E", (), {"extract": lambda self, q: []})()
    res = router.route("who fixed issue #7?", top_k=5)
    assert res.trace_log["execution_path"]["linked_seeds"] == ["i"]
    assert res.facts == ["Issue #7 <-> pr: RESOLVES"]


def test_facts_survive_when_the_node_misses_the_top_k():
    """The PR that answers the question can rank below the cut; its link must not."""
    router = make_router(
        hits=[hit("issue", 0.9, ntype="Ticket", label="Issue #1")],
        neighbours={"issue": [nbr("pr", config.RELATION_RESOLVES)]},
    )
    res = router.route("which pr fixed this", top_k=1)
    assert [r.id for r in res.results] == ["issue"]
    assert res.facts == ["Issue #1 <-> pr: RESOLVES"]


def test_trace_log_exposes_relations_and_recency():
    """The viewer can only show why something ranked if the trace says so."""
    router = make_router(
        hits=[hit("seed", 0.9, ts=int(NOW - 10 * DAY))],
        neighbours={"seed": [nbr("pr", config.RELATION_RESOLVES)]},
    )
    res = router.route("who fixed it?", top_k=10)

    hops = res.trace_log["execution_path"]["graph_hops"]
    assert hops and hops[0]["relation"] == config.RELATION_RESOLVES

    recency = res.trace_log["recency"]
    assert recency["enabled"] is True
    applied = {a["id"]: a for a in recency["applied"]}
    assert applied["seed"]["age_days"] == pytest.approx(10, abs=0.5)
    assert 0 < applied["seed"]["factor"] < 1


def test_recency_can_be_disabled(monkeypatch):
    monkeypatch.setattr(config, "RECENCY_ENABLED", False)
    router = make_router(
        hits=[hit("stale", 0.91, ts=int(NOW - 400 * DAY)), hit("fresh", 0.60, ts=int(NOW))],
        neighbours={},
    )
    res = router.route("explain what broke", top_k=10)
    assert res.results[0].id == "stale"  # pure similarity ordering restored


if __name__ == "__main__":
    pytest.main([__file__, "-q"])


def test_remembered_facts_have_their_own_budget():
    from tracerag.router import graph_facts

    hops = [{"from_id": f"p{i}", "to_id": "svc", "relation": "AUTHORED", "origin": "api"} for i in range(30)]
    hops.append({"from_id": "svc", "to_id": "team", "relation": "OWNED_BY", "origin": "agent", "source": "r1"})
    out = graph_facts(hops, {})
    assert out[0] == "svc <-> team: OWNED_BY (remembered, source: r1)"
    assert len(out) == config.GRAPH_MAX_FACTS + 1
