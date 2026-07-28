"""GitHub payloads -> typed, timestamped edges. No DB, no embedder."""
import pytest

from tracerag import config
from tracerag.github_graph import GitHubGraphBuilder, parse_ts


class FakeDB:
    """Records what the builder would write."""

    def __init__(self):
        self.nodes = {}
        self.edges = []

    def upsert_node(self, node_id, label, node_type, embedding, ts=0):
        prev = self.nodes.get(node_id)
        # mirror the real upsert: ts only moves forward
        if prev and prev["ts"] > ts:
            ts = prev["ts"]
        self.nodes[node_id] = {"label": label, "type": node_type, "ts": ts}

    def add_relationship(self, a, b, confidence=None, relation=config.RELATION_CO_OCCURS, ts=0):
        self.edges.append({"from": a, "to": b, "relation": relation, "ts": ts})

    def rel(self, relation):
        return [e for e in self.edges if e["relation"] == relation]


@pytest.fixture
def build():
    db = FakeDB()
    return db, GitHubGraphBuilder(db, lambda text: [0.0] * config.EMBED_DIM, "acme/platform")


PR = {
    "number": 4977,
    "title": "chore: bump stripe-sdk 11.2 -> 12.0",
    "merged_at": "2026-07-24T09:12:31Z",
    "created_at": "2026-07-23T10:00:00Z",
    "user": {"login": "lena"},
    "reviews": [{"user": {"login": "marco"}}, {"user": {"login": "marco"}}],
    "body": "Routine upgrade. Fixes #2291 and closes #2280.",
    "files": [{"filename": "services/payment/auth.py"}],
}


def test_parse_ts():
    assert parse_ts("2026-07-24T09:12:31Z") > 0
    assert parse_ts(None) == 0
    assert parse_ts("not a date") == 0


def test_pull_request_emits_every_structural_relation(build):
    db, b = build
    from tracerag.github_graph import GraphStats
    b.add_pull_request(PR, GraphStats())

    authored = db.rel(config.RELATION_AUTHORED)
    assert len(authored) == 1
    assert authored[0]["from"] == "person:lena"
    assert authored[0]["to"] == "pr:acme/platform#4977"

    assert len(db.rel(config.RELATION_REVIEWED)) == 1
    # both "Fixes #2291" and "closes #2280" become causal edges
    assert {e["to"] for e in db.rel(config.RELATION_RESOLVES)} == {
        "issue:acme/platform#2291", "issue:acme/platform#2280"
    }
    touches = {e["to"] for e in db.rel(config.RELATION_TOUCHES)}
    assert "file:acme/platform:services/payment/auth.py" in touches


def test_merge_time_lands_on_the_pr_node(build):
    db, b = build
    from tracerag.github_graph import GraphStats
    b.add_pull_request(PR, GraphStats())
    node = db.nodes["pr:acme/platform#4977"]
    assert node["ts"] == parse_ts("2026-07-24T09:12:31Z")  # merged_at, not created_at
    assert node["type"] == "PR"


def test_no_co_occurrence_edges_from_structured_input(build):
    db, b = build
    from tracerag.github_graph import GraphStats
    b.add_pull_request(PR, GraphStats())
    assert db.rel(config.RELATION_CO_OCCURS) == []


def test_issues_endpoint_skips_pull_requests(build):
    db, b = build
    from tracerag.github_graph import GraphStats
    stats = GraphStats()
    b.add_issue({"number": 1, "pull_request": {}, "created_at": "2026-07-01T00:00:00Z"}, stats)
    assert db.edges == []
    b.add_issue({"number": 2291, "title": "sev1", "created_at": "2026-07-23T00:00:00Z",
                 "user": {"login": "ana"}}, stats)
    assert len(db.rel(config.RELATION_REPORTED)) == 1


def test_commit_author_and_closes(build):
    db, b = build
    from tracerag.github_graph import GraphStats
    b.add_commit({
        "sha": "7a2b4159fbc",
        "commit": {"message": "fix auth flow\n\nFixes #2291",
                   "author": {"date": "2026-07-24T08:00:00Z", "name": "Lena K."}},
        "author": {"login": "lena"},
    }, GraphStats())
    assert db.rel(config.RELATION_AUTHORED)[0]["from"] == "person:lena"
    assert db.rel(config.RELATION_RESOLVES)[0]["to"] == "issue:acme/platform#2291"
    assert db.nodes["commit:acme/platform:7a2b415"]["type"] == "Commit"


def test_build_counts_relations(build):
    db, b = build
    stats = b.build(pulls=[PR], issues=[], commits=[])
    assert stats.edges == len(db.edges)
    assert stats.by_relation[config.RELATION_AUTHORED] == 1
    assert stats.nodes > 0


def test_structural_edges_outweigh_proximity():
    """The whole point of typing edges: a real relation must beat a guess."""
    authored = config.RELATION_WEIGHTS[config.RELATION_AUTHORED]
    co = config.RELATION_WEIGHTS[config.RELATION_CO_OCCURS]
    assert authored > co
    # even a 2-hop structural path beats a 1-hop proximity hop
    assert authored * config.RELATION_WEIGHTS[config.RELATION_RESOLVES] > co


if __name__ == "__main__":
    pytest.main([__file__, "-q"])


def test_requested_reviewers_are_not_counted_as_reviews(build):
    """`requested_reviewers` is a pending ask, not a completed review — crediting
    it would claim someone reviewed code they never opened."""
    db, b = build
    from tracerag.github_graph import GraphStats
    b.add_pull_request(
        {"number": 1, "user": {"login": "lena"},
         "requested_reviewers": [{"login": "nobody"}]}, GraphStats())
    assert db.rel(config.RELATION_REVIEWED) == []


def test_self_approval_is_not_a_review(build):
    db, b = build
    from tracerag.github_graph import GraphStats
    b.add_pull_request(
        {"number": 2, "user": {"login": "lena"},
         "reviews": [{"user": {"login": "lena"}}]}, GraphStats())
    assert db.rel(config.RELATION_REVIEWED) == []


def test_repeat_reviews_collapse_to_one_edge(build):
    db, b = build
    from tracerag.github_graph import GraphStats
    stats = GraphStats()
    b.add_pull_request(
        {"number": 3, "user": {"login": "lena"},
         "reviews": [{"user": {"login": "marco"}}] * 4}, stats)
    assert len(db.rel(config.RELATION_REVIEWED)) == 1
    assert stats.by_relation[config.RELATION_REVIEWED] == 1


def test_naive_timestamps_are_read_as_utc():
    """A tz-less string would otherwise take the machine's offset and shift ages."""
    assert parse_ts("2026-01-01T00:00:00") == parse_ts("2026-01-01T00:00:00Z")
