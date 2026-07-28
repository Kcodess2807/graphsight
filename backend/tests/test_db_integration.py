"""End-to-end against a real .lbug store.

The unit tests exercise the scoring maths against a fake store; these run the
actual DDL, MERGE ... ON MATCH clauses and vector index through LadybugDB, so a
Cypher typo or a bad migration fails here instead of in production.

Skipped when the driver isn't installed:  pip install ladybug
"""
import shutil
import time

import pytest

lb = pytest.importorskip("ladybug", reason="LadybugDB driver not installed")

from tracerag import config                                   # noqa: E402
from tracerag.db import TraceDB                               # noqa: E402
from tracerag.github_graph import GitHubGraphBuilder          # noqa: E402
from tracerag.router import TraceRouter                       # noqa: E402

DAY = 86400
NOW = int(time.time())


def vec(*weights: float) -> list[float]:
    """Unit-ish embedding: the given weights, zero-padded to EMBED_DIM."""
    v = list(weights) + [0.0] * (config.EMBED_DIM - len(weights))
    return [float(x) for x in v]


QUERY_VEC = vec(1.0)
NEAR = vec(0.93, 0.37)   # cosine ~0.93 to QUERY_VEC
FAR = vec(0.45, 0.89)    # cosine ~0.45


@pytest.fixture
def db(tmp_path):
    store = tmp_path / "t.lbug"
    d = TraceDB(store, pool_size=2)
    d.init_schema()
    yield d
    d.close()
    shutil.rmtree(store, ignore_errors=True)


def add(d: TraceDB, node_id, label, ntype, embedding=None, ts=0):
    d.upsert_node(node_id, label, ntype, embedding or vec(0.5, 0.5), ts=ts)
    return node_id


# --- schema ---------------------------------------------------------------

def test_schema_has_the_new_columns(db):
    assert "ts" in db.table_columns(config.NODE_TABLE)
    assert {"relation", "ts"} <= db.table_columns(config.REL_TABLE)


def test_fresh_store_needs_no_migration(db):
    assert db.migrate_schema() == []


def test_pre_03_store_migrates_in_place(tmp_path):
    """An old .lbug must keep its data and gain the columns — not be deleted."""
    store = tmp_path / "old.lbug"
    raw = lb.Database(str(store))
    conn = lb.Connection(raw)
    conn.execute(
        f"CREATE NODE TABLE {config.NODE_TABLE} (id STRING PRIMARY KEY, "
        f"label STRING, type STRING, embedding FLOAT[{config.EMBED_DIM}]);"
    )
    conn.execute(
        f"CREATE REL TABLE {config.REL_TABLE} "
        f"(FROM {config.NODE_TABLE} TO {config.NODE_TABLE}, confidence DOUBLE);"
    )
    conn.execute(
        f"CREATE (:{config.NODE_TABLE} {{id:'legacy', label:'Legacy', "
        f"type:'PR', embedding:{QUERY_VEC}}});"
    )
    conn.execute(
        f"CREATE (:{config.NODE_TABLE} {{id:'legacy2', label:'Legacy2', "
        f"type:'PR', embedding:{FAR}}});"
    )
    # the old writer stored every edge at a degenerate 1.0
    conn.execute(
        f"MATCH (a:{config.NODE_TABLE}{{id:'legacy'}}), "
        f"(b:{config.NODE_TABLE}{{id:'legacy2'}}) "
        f"CREATE (a)-[:{config.REL_TABLE} {{confidence: 1.0}}]->(b);"
    )
    conn.close()
    raw.close()

    d = TraceDB(store, pool_size=1)
    added = d.migrate_schema()
    assert set(added) == {
        f"{config.NODE_TABLE}.ts",
        f"{config.REL_TABLE}.relation",
        f"{config.REL_TABLE}.ts",
    }
    # the pre-existing rows survived and read back with the column default
    rows = d._fetch(
        f"MATCH (e:{config.NODE_TABLE}) RETURN e.id AS id, e.ts AS ts "
        f"ORDER BY e.id;")
    assert rows == [{"id": "legacy", "ts": 0}, {"id": "legacy2", "ts": 0}]
    assert edge(d)["relation"] == config.RELATION_CO_OCCURS

    # the degenerate 1.0 is repriced, so a typed relation can now outrank it
    legacy_conf = edge(d)["confidence"]
    assert legacy_conf == pytest.approx(
        config.RELATION_WEIGHTS[config.RELATION_CO_OCCURS])
    assert legacy_conf < config.RELATION_WEIGHTS[config.RELATION_AUTHORED]

    # ...and upgrade it, which a 1.0 edge could never have allowed
    d.add_relationship("legacy", "legacy2",
                       relation=config.RELATION_AUTHORED, ts=NOW)
    assert edge(d)["relation"] == config.RELATION_AUTHORED

    # the migrated store accepts a fresh typed, timestamped write
    add(d, "new", "New", "PR", NEAR, ts=NOW)
    d.add_relationship("legacy", "new", relation=config.RELATION_RESOLVES, ts=NOW)
    assert d.migrate_schema() == []  # idempotent
    d.close()


# --- nodes ----------------------------------------------------------------

def test_node_timestamp_only_moves_forward(db):
    add(db, "n", "N", "PR", ts=NOW - 10 * DAY)
    add(db, "n", "N", "PR", ts=NOW)            # newer event wins
    add(db, "n", "N", "PR", ts=NOW - 90 * DAY)  # older event must not roll it back
    rows = db._fetch(
        f"MATCH (e:{config.NODE_TABLE} {{id:'n'}}) RETURN e.ts AS ts;")
    assert rows[0]["ts"] == NOW


def test_undated_rewrite_over_a_dated_row_does_not_overflow(db):
    """Regression: $ts=0 was inferred as INT8, so the CASE overflowed against a
    real epoch value. Re-ingesting an undated item must just be a no-op."""
    add(db, "n", "N", "PR", ts=NOW)
    add(db, "n", "N", "PR", ts=0)
    add(db, "m", "M", "PR")
    db.add_relationship("n", "m", relation=config.RELATION_AUTHORED, ts=NOW)
    db.add_relationship("n", "m", relation=config.RELATION_AUTHORED, ts=0)
    node = db._fetch(
        f"MATCH (e:{config.NODE_TABLE} {{id:'n'}}) RETURN e.ts AS ts;")
    assert node[0]["ts"] == NOW
    assert edge(db)["ts"] == NOW


# --- edges ----------------------------------------------------------------

def edge(db) -> dict:
    rows = db._fetch(
        f"MATCH ()-[r:{config.REL_TABLE}]->() "
        f"RETURN r.confidence AS confidence, r.relation AS relation, r.ts AS ts;")
    return rows[0]


def test_relation_defaults_to_its_configured_weight(db):
    add(db, "a", "A", "Person")
    add(db, "b", "B", "PR")
    db.add_relationship("a", "b", relation=config.RELATION_AUTHORED, ts=NOW)
    e = edge(db)
    assert e["relation"] == config.RELATION_AUTHORED
    assert e["confidence"] == pytest.approx(
        config.RELATION_WEIGHTS[config.RELATION_AUTHORED])
    assert e["ts"] == NOW


def test_proximity_edge_upgrades_when_structure_proves_it(db):
    add(db, "a", "A", "Person")
    add(db, "b", "B", "PR")
    db.add_relationship("a", "b", relation=config.RELATION_CO_OCCURS)
    db.add_relationship("a", "b", relation=config.RELATION_AUTHORED, ts=NOW)
    e = edge(db)
    assert e["relation"] == config.RELATION_AUTHORED
    assert e["confidence"] == pytest.approx(
        config.RELATION_WEIGHTS[config.RELATION_AUTHORED])


def test_a_later_guess_never_downgrades_a_known_edge(db):
    add(db, "a", "A", "Person")
    add(db, "b", "B", "PR")
    db.add_relationship("a", "b", relation=config.RELATION_AUTHORED, ts=NOW)
    db.add_relationship("a", "b", relation=config.RELATION_CO_OCCURS)
    assert edge(db)["relation"] == config.RELATION_AUTHORED


def test_expand_frontier_carries_relation_and_ts(db):
    add(db, "a", "A", "Person")
    add(db, "b", "B", "PR", ts=NOW - 3 * DAY)
    db.add_relationship("a", "b", relation=config.RELATION_AUTHORED, ts=NOW)
    nbrs = db.expand_frontier(["a"], k=5, max_degree=10)["a"]
    assert nbrs[0]["relation"] == config.RELATION_AUTHORED
    assert nbrs[0]["ts"] == NOW - 3 * DAY


def test_a_wide_diff_does_not_hide_a_pr_from_traversal(db):
    """Regression: --files gave real PRs enough TOUCHES edges to trip the hub
    filter, so 47% of pallets/click's PRs became untraversable."""
    add(db, "pr", "PR #1", "PR")
    add(db, "author", "vishal", "Person")
    db.add_relationship("author", "pr", relation=config.RELATION_AUTHORED)
    for i in range(30):  # a wide refactor
        add(db, f"f{i}", f"src/mod{i}.py", "File")
        db.add_relationship("pr", f"f{i}", relation=config.RELATION_TOUCHES)

    nbrs = db.expand_frontier(["pr"], k=5, max_degree=10).get("pr", [])
    relations = {n["relation"] for n in nbrs}
    assert relations == {config.RELATION_AUTHORED}, (
        "the over-wide TOUCHES fan-out should drop, the author link should not")


def test_a_true_hub_is_still_skipped(db):
    """Every relation fanning out too wide means the node carries no signal."""
    add(db, "repo", "acme/api", "Repo")
    for i in range(30):
        add(db, f"p{i}", f"PR #{i}", "PR")
        db.add_relationship(f"p{i}", "repo", relation=config.RELATION_TOUCHES)
        db.add_relationship(f"p{i}", "repo", relation=config.RELATION_PART_OF)
    assert db.expand_frontier(["repo"], k=5, max_degree=10) == {}


def test_subgraph_carries_relation_for_the_canvas(db):
    add(db, "a", "A", "Person")
    add(db, "b", "B", "PR")
    db.add_relationship("a", "b", relation=config.RELATION_AUTHORED, ts=NOW)
    sub = db.subgraph(["a"])
    assert sub["edges"][0]["relation"] == config.RELATION_AUTHORED


def test_vector_search_carries_ts(db):
    add(db, "a", "A", "PR", NEAR, ts=NOW - 5 * DAY)
    db.build_vector_index()
    hit = db.vector_search(QUERY_VEC, k=1)[0]
    assert hit["id"] == "a"
    assert hit["ts"] == NOW - 5 * DAY


# --- github builder against the real store --------------------------------

PULL = {
    "number": 412, "title": "Fix token refresh", "merged_at": "2026-07-27T10:00:00Z",
    "user": {"login": "vishal"},
    "reviews": [{"user": {"login": "arush"}}],
    "body": "Fixes #77",
    "files": [{"filename": "auth/session.py"}],
}


def test_builder_writes_typed_edges_into_a_real_store(db):
    b = GitHubGraphBuilder(db, lambda text: vec(0.5, 0.5), "acme/api")
    stats = b.build(pulls=[PULL])
    rows = db._fetch(
        f"MATCH (a:{config.NODE_TABLE})-[r:{config.REL_TABLE}]->"
        f"(c:{config.NODE_TABLE}) "
        f"RETURN a.id AS src, c.id AS dst, r.relation AS relation;")
    seen = {(r["src"], r["dst"], r["relation"]) for r in rows}
    assert ("person:vishal", "pr:acme/api#412",
            config.RELATION_AUTHORED) in seen
    assert ("person:arush", "pr:acme/api#412",
            config.RELATION_REVIEWED) in seen
    assert ("pr:acme/api#412", "issue:acme/api#77",
            config.RELATION_RESOLVES) in seen
    assert ("pr:acme/api#412", "file:acme/api:auth/session.py",
            config.RELATION_TOUCHES) in seen
    assert stats.edges == len(rows)


# --- the whole thing ------------------------------------------------------

def test_stale_but_similar_loses_to_fresh_and_connected(db):
    """The failure demo, run through the real DB rather than a fake one."""
    stale_ts = NOW - 240 * DAY
    fresh_ts = NOW - 1 * DAY
    add(db, "pr:stale", "PR #101", "PR", NEAR, ts=stale_ts)
    add(db, "pr:fresh", "PR #412", "PR", FAR, ts=fresh_ts)
    add(db, "person:vishal", "vishal", "Person", vec(0.4, 0.4, 0.4))
    db.add_relationship("person:vishal", "pr:fresh",
                        relation=config.RELATION_AUTHORED, ts=fresh_ts)
    db.add_relationship("pr:stale", "person:vishal",
                        relation=config.RELATION_CO_OCCURS)
    db.build_vector_index()

    router = TraceRouter(db)
    router._encode = lambda text: QUERY_VEC     # skip the real embedder

    # vector-only sanity: the stale PR genuinely looks more similar
    hits = {h["id"]: h["similarity"] for h in db.vector_search(QUERY_VEC, k=5)}
    assert hits["pr:stale"] > hits["pr:fresh"]

    res = router.route("who owns the code that broke?", top_k=10)
    ranked = [r.id for r in res.results]
    assert ranked.index("pr:fresh") < ranked.index("pr:stale"), ranked

    by_id = {r.id: r for r in res.results}
    assert by_id["pr:stale"].recency < by_id["pr:fresh"].recency
    assert by_id["pr:stale"].age_days == pytest.approx(240, abs=1)

    hops = res.trace_log["execution_path"]["graph_hops"]
    assert {h["relation"] for h in hops} >= {config.RELATION_AUTHORED}
    assert res.trace_log["recency"]["enabled"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
