"""Memory end to end on a tiny snapshot: load, remember, recall, replace, retract.
Offline: a hashed stand-in replaces the embedding model."""

import hashlib

import pytest

from graphsight_memory import RELATIONS, Memory

SNAPSHOT = {
    "pulls": [
        {"number": 7, "title": "Speed up the checkout path", "body": "Fixes #3",
         "merged_at": "2026-11-01T10:00:00Z", "user": {"login": "alice"},
         "files": [{"filename": "src/checkout.py"}], "reviews": [{"user": {"login": "bob"}}]},
        {"number": 8, "title": "Docs for refunds", "body": "",
         "merged_at": "2026-11-02T10:00:00Z", "user": {"login": "carol"},
         "files": [{"filename": "docs/refunds.md"}], "reviews": []},
    ],
    "issues": [{"number": 3, "title": "Checkout is slow", "body": "",
                "created_at": "2026-10-30T10:00:00Z", "user": {"login": "dave"}}],
    "commits": [],
}


def embed(text: str) -> list[float]:
    """Deterministic 384-dim unit vector from a hash: no model download."""
    raw = hashlib.sha256(text.encode()).digest() * 12
    v = [b - 127.5 for b in raw[:384]]
    norm = sum(x * x for x in v) ** 0.5
    return [x / norm for x in v]


@pytest.fixture
def mem(tmp_path):
    m = Memory(tmp_path / "t.lbug", embed=embed)
    m.load("acme/shop", SNAPSHOT)
    yield m
    m.close()


def remembered(recall) -> list[str]:
    return [f.text for f in recall.facts if f.remembered]


def test_github_facts_are_typed_and_directed(mem):
    facts = [f.text for f in mem.recall("who authored PR #7?").facts]
    assert "alice AUTHORED PR #7" in facts
    assert "PR #7 RESOLVES Issue #3" in facts


def test_a_told_fact_joins_to_github(mem):
    """The join the graph is for: team -> file -> PR -> author, three hops."""
    mem.remember("src/checkout.py", "owned by", "payments team", source="standup")
    r = mem.recall("Who authored the PR that touches the file the payments team owns?")
    texts = [f.text for f in r.facts]
    assert "src/checkout.py OWNED_BY payments team" in texts
    assert "alice AUTHORED PR #7" in texts
    assert [f.source for f in r.facts if f.remembered] == ["standup"]
    assert "alice" in str(r)


def test_replace_then_retract(mem):
    mem.remember("src/checkout.py", "OWNED_BY", "payments team", source="a")
    mem.remember("src/checkout.py", "OWNED_BY", "billing team", source="b", replace=True)
    assert remembered(mem.recall("which team owns src/checkout.py?")) == ["src/checkout.py OWNED_BY billing team"]
    assert mem.retract("src/checkout.py", "OWNED_BY") == 1
    assert remembered(mem.recall("which team owns src/checkout.py?")) == []


def test_forget_never_touches_github(mem):
    assert mem.forget("PR #7", "TOUCHES", "src/checkout.py") == 0
    assert "PR #7 TOUCHES src/checkout.py" in [f.text for f in mem.recall("what did PR #7 touch?").facts]


def test_unknown_relations_are_refused_unless_allowed(tmp_path):
    with Memory(tmp_path / "a.lbug", embed=embed) as m:
        with pytest.raises(ValueError, match="unknown relation LIKES"):
            m.remember("x", "likes", "y", source="s")
    with Memory(tmp_path / "b.lbug", embed=embed, relations=None) as m:
        assert m.remember("x", "likes", "y", source="s")["relation"] == "LIKES"


def test_every_relation_example_reads_subject_relation_object():
    for name, example in RELATIONS.items():
        assert f" {name} " in example, name


def test_learn_without_an_llm_says_what_to_do(mem, monkeypatch):
    from graphsight_memory import config
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", None)
    with pytest.raises(RuntimeError, match="learn\\(\\) needs an LLM"):
        mem.learn("alice owns checkout", source="s")


def test_learn_keeps_only_known_relations(mem):
    class LLM:
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    assert "relation must be one of" in kw["messages"][0]["content"]
                    reply = ('{"facts": [{"subject": "src/checkout.py", "relation": "OWNED_BY", "object": "payments team"},'
                             ' {"subject": "alice", "relation": "LIKES", "object": "tea"}]}')
                    msg = type("M", (), {"content": reply})()
                    return type("R", (), {"choices": [type("C", (), {"message": msg})()]})()
    stored = mem.learn("payments owns checkout; alice likes tea", source="chat", llm=LLM, model="m")
    assert [s["relation"] for s in stored] == ["OWNED_BY"]
