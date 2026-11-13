"""Agent-written memory against a real .lbug store: write, replace, forget, and
the line between an agent's facts and the source system's."""
import shutil

import pytest

lb = pytest.importorskip("ladybug", reason="LadybugDB driver not installed")

from tracerag import config                     # noqa: E402
from tracerag.db import TraceDB                 # noqa: E402
from tracerag.memory import AgentMemory         # noqa: E402
from tracerag.router import TraceRouter         # noqa: E402

TEAM_A = [1.0] + [0.0] * (config.EMBED_DIM - 1)


def embed(text: str) -> list[float]:
    """Deterministic stand-in for the real embedder: one hot slot per name."""
    v = [0.0] * config.EMBED_DIM
    v[sum(map(ord, text)) % config.EMBED_DIM] = 1.0
    return v


@pytest.fixture
def db(tmp_path):
    store = tmp_path / "m.lbug"
    d = TraceDB(store, pool_size=2)
    d.init_schema()
    d.upsert_node("service:checkout", "checkout-service", "Service", embed("checkout-service"))
    d.upsert_node("pr:a/b#7", "PR #7", "PR", embed("PR #7"))
    d.add_relationship("pr:a/b#7", "service:checkout", relation=config.RELATION_TOUCHES, ts=1)
    d.build_vector_index()  # memory must work with the index live, as it is in serving
    yield d
    d.close()
    shutil.rmtree(store, ignore_errors=True)


def router(db: TraceDB) -> TraceRouter:
    r = TraceRouter(db)
    r._encode = embed
    r._get_extractor = lambda: type("E", (), {"extract": lambda self, q: []})()
    r._classify_intent = lambda q: (0.15, 0.85, "relational")  # no live model in tests
    return r


def has_fact(found: list[str], a: str, b: str, relation: str, remembered: bool) -> bool:
    """Facts are undirected, so either end can print first."""
    return any(a in f and b in f and f": {relation}" in f and ("remembered" in f) == remembered
               for f in found)


def facts(db: TraceDB, question: str) -> list[str]:
    return router(db).route(question, top_k=10).facts


def agent_edges(db: TraceDB) -> list[dict]:
    return db._fetch(
        f"MATCH (a)-[r:{config.REL_TABLE}]->(b) WHERE r.origin = 'agent' "
        f"RETURN a.label AS a, r.relation AS rel, b.label AS b, r.ended AS ended, "
        f"r.source AS source ORDER BY b.label;")


def test_a_remembered_fact_is_retrieved_and_labelled(db):
    AgentMemory(db, embed).remember("checkout-service", "owned by", "payments team", source="run-1")
    found = facts(db, "checkout-service")
    assert any(f.endswith(": OWNED_BY (remembered, source: run-1)") for f in found)
    # the GitHub fact on the same node is still there, and unlabelled
    assert has_fact(found, "PR #7", "checkout-service", "TOUCHES", remembered=False)


def test_a_new_name_becomes_a_searchable_node(db):
    AgentMemory(db, embed).remember("checkout-service", "owned by", "payments team", source="run-1")
    hits = [h["id"] for h in db.vector_search(embed("payments team"), k=3)]
    assert "mem:payments-team" in hits


def test_replacing_ends_the_old_fact_but_keeps_its_history(db):
    memory = AgentMemory(db, embed)
    memory.remember("checkout-service", "owned by", "payments team", source="run-1")
    result = memory.remember("checkout-service", "owned by", "billing team",
                             source="run-2", replace=True)
    assert result["replaced"] == 1
    found = " ".join(facts(db, "checkout-service"))
    assert "billing team" in found and "payments team" not in found
    history = {e["b"]: e["ended"] for e in agent_edges(db)}
    assert history["payments team"] > 0 and history["billing team"] == 0
    # walking from the node whose only fact ended must not crash or resurrect it
    assert not any("payments team" in f for f in facts(db, "payments team"))


def test_without_replace_both_facts_stand(db):
    memory = AgentMemory(db, embed)
    memory.remember("checkout-service", "owned by", "payments team", source="run-1")
    memory.remember("checkout-service", "owned by", "billing team", source="run-2")
    assert all(e["ended"] == 0 for e in agent_edges(db))


def test_forget_removes_the_fact_and_the_node_it_created(db):
    memory = AgentMemory(db, embed)
    memory.remember("checkout-service", "owned by", "payments team", source="run-1")
    assert memory.forget("checkout-service", "OWNED_BY", "payments team") == 1
    assert agent_edges(db) == []
    assert "payments team" not in " ".join(facts(db, "checkout-service"))
    assert "mem:payments-team" not in [h["id"] for h in db.vector_search(embed("payments team"), k=3)]


def test_forget_cannot_touch_a_github_fact(db):
    assert AgentMemory(db, embed).forget("PR #7", "TOUCHES", "checkout-service") == 0
    assert has_fact(facts(db, "checkout-service"), "PR #7", "checkout-service", "TOUCHES", remembered=False)


def test_ingest_never_rewrites_an_agent_fact_on_the_same_pair(db):
    AgentMemory(db, embed).remember("PR #7", "broke", "checkout-service", source="run-1")
    # a stronger API relation on the same pair must not "upgrade" the agent's edge
    db.add_relationship("pr:a/b#7", "service:checkout", relation=config.RELATION_AUTHORED, ts=2)
    assert [(e["rel"], e["source"]) for e in agent_edges(db)] == [("BROKE", "run-1")]


def test_an_agent_fact_ranks_below_a_github_fact(db):
    AgentMemory(db, embed).remember("PR #7", "broke", "checkout-service", source="run-1")
    neighbours = db.expand_frontier(["pr:a/b#7"], k=5, max_degree=10)["pr:a/b#7"]
    assert [n["origin"] for n in neighbours] == ["api", "agent"]


@pytest.mark.parametrize("subject,relation,obj", [
    ("", "OWNED_BY", "x"),
    ("x", "; --", "y"),
    ("x", "9 lives", "y"),
    ("x", "", "y"),
    ("x" * 201, "OWNED_BY", "y"),
])
def test_bad_input_is_refused(db, subject, relation, obj):
    with pytest.raises(ValueError):
        AgentMemory(db, embed).remember(subject, relation, obj, source="t")


def test_mcp_writes_need_the_configured_token(db, monkeypatch):
    import mcp_server

    r = router(db)
    monkeypatch.setattr(mcp_server, "get_current_tenant", lambda: mcp_server.Tenant(router=r, db=db))
    monkeypatch.setattr(config, "MCP_WRITE_TOKEN", None)
    assert not mcp_server._remember_impl("anything", "a", "OWNS", "b", False)["ok"]

    monkeypatch.setattr(config, "MCP_WRITE_TOKEN", "s3cret")
    assert not mcp_server._remember_impl("wrong", "a", "OWNS", "b", False)["ok"]
    assert not mcp_server._forget_impl("", "a", "OWNS", "b")["ok"]
    assert agent_edges(db) == []

    assert mcp_server._remember_impl("s3cret", "checkout-service", "OWNED_BY", "payments team", False)["ok"]
    assert agent_edges(db)[0]["source"] == "mcp"
    assert mcp_server._forget_impl("s3cret", "checkout-service", "OWNED_BY", "payments team")["removed"] == 1
    assert mcp_server._remember_impl("s3cret", "", "OWNED_BY", "x", False)["ok"] is False


class FakeLLM:
    """Answers every chat call with a fixed reply, like the OpenAI client shape."""

    def __init__(self, reply):
        msg = type("M", (), {"content": reply})()
        resp = type("R", (), {"choices": [type("C", (), {"message": msg})()]})()
        self.chat = type("Ch", (), {"completions": type("Co", (), {"create": lambda s, **k: resp})()})()


def test_learn_stores_what_the_model_extracts_and_skips_bad_facts(db):
    reply = """Sure: {"facts": [
        {"subject": "checkout-service", "relation": "OWNED_BY", "object": "payments team"},
        {"subject": "", "relation": "OWNED_BY", "object": "nobody"},
        {"relation": "missing subject"}]}"""
    stored = AgentMemory(db, embed).learn("x", FakeLLM(reply), "m", source="msg-1")
    assert [(f["relation"], f["object"]) for f in stored] == [("OWNED_BY", "mem:payments-team")]


def test_learn_passes_replace_through(db):
    memory = AgentMemory(db, embed)
    memory.remember("checkout-service", "OWNED_BY", "payments team", source="msg-1")
    reply = '{"facts": [{"subject": "checkout-service", "relation": "OWNED_BY", "object": "billing team", "replaces_previous": true}]}'
    assert memory.learn("moved", FakeLLM(reply), "m", source="msg-2")[0]["replaced"] == 1


def test_learn_survives_a_reply_that_is_not_json(db):
    assert AgentMemory(db, embed).learn("x", FakeLLM("I can't help with that."), "m", source="s") == []


def test_an_agent_fact_survives_a_busy_node(db):
    """The walk keeps the top k neighbours by weight; an agent fact must not be cut."""
    for i in range(8):
        db.upsert_node(f"pr:a/b#{i + 10}", f"PR #{i + 10}", "PR", embed(f"PR #{i + 10}"))
        db.add_relationship(f"pr:a/b#{i + 10}", "service:checkout", relation=config.RELATION_AUTHORED, ts=1)
    AgentMemory(db, embed).remember("checkout-service", "owned by", "payments team", source="run-1")
    neighbours = db.expand_frontier(["service:checkout"], k=5, max_degree=20)["service:checkout"]
    assert "mem:payments-team" in [n["id"] for n in neighbours]


def test_retract_ends_a_fact_with_nothing_in_its_place(db):
    memory = AgentMemory(db, embed)
    memory.remember("checkout-service", "owned by", "payments team", source="run-1")
    assert memory.retract("checkout-service", "OWNED_BY") == 1
    assert not any("payments team" in f for f in facts(db, "checkout-service"))
    assert [e["ended"] > 0 for e in agent_edges(db)] == [True]


def test_learn_passes_a_retraction_through(db):
    memory = AgentMemory(db, embed)
    memory.remember("checkout-service", "OWNED_BY", "payments team", source="msg-1")
    reply = '{"facts": [{"subject": "checkout-service", "relation": "OWNED_BY", "object": null, "retracts": true}]}'
    assert memory.learn("no owner now", FakeLLM(reply), "m", source="msg-2")[0]["retracted"] == 1
