"""Episodic recall tests: what gets remembered, and what must not be."""
import json

import pytest
from langchain_core.documents import Document

from graphsight_langgraph import (
    AgentTrace,
    EpisodeRetriever,
    LangGraphTracer,
    Retrieval,
    RetrievedItem,
    capture,
    recall,
    save_trace,
)
from graphsight_langgraph.mapper import to_tracestate


def save(dir, name, query, answer="an answer", outcome="success", when="2026-11-01T00:00:00Z"):
    (dir / name).write_text(
        json.dumps({"query": query, "answer": answer, "outcome": outcome,
                    "computedAt": when, "graph": {"nodes": [], "edges": []}}),
        encoding="utf-8",
    )


def test_recall_finds_the_matching_run_best_first(tmp_path):
    save(tmp_path, "a.json", "who changed option parsing?")
    save(tmp_path, "b.json", "who changed parsing in decorators?")
    save(tmp_path, "c.json", "what is the release process?")
    found = recall("who changed option parsing?", dir=tmp_path)
    assert found[0].file == "a.json"
    assert "c.json" not in [e.file for e in found]


def test_failed_and_unlabelled_runs_are_never_recalled(tmp_path):
    save(tmp_path, "bad.json", "who broke checkout?", outcome="failure")
    save(tmp_path, "unjudged.json", "who broke checkout?", outcome=None)
    assert recall("who broke checkout?", dir=tmp_path) == []
    found = recall("who broke checkout?", dir=tmp_path, outcome="failure")
    assert [e.file for e in found] == ["bad.json"]


def test_repeats_collapse_to_the_newest_copy(tmp_path):
    save(tmp_path, "old.json", "who broke checkout?", answer="old", when="2026-01-01T00:00:00Z")
    save(tmp_path, "new.json", "who broke checkout?", answer="new", when="2026-11-01T00:00:00Z")
    assert [e.answer for e in recall("who broke checkout?", dir=tmp_path)] == ["new"]


def test_unreadable_files_and_missing_dirs_are_empty_not_errors(tmp_path):
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "list.json").write_text("[1, 2]", encoding="utf-8")
    assert recall("anything at all", dir=tmp_path) == []
    assert recall("anything at all", dir=tmp_path / "nope") == []


def test_used_sources_come_from_measured_overlap(tmp_path):
    trace = AgentTrace(query="who broke checkout?", answer="PR 412 did", outcome="success")
    trace.retrievals.append(Retrieval(span_id="s", query="q", items=[
        RetrievedItem(id="a", label="PR #412", content="x", answer_overlap=0.8),
        RetrievedItem(id="b", label="PR #1", content="y", answer_overlap=0.0),
        RetrievedItem(id="episode:old.json", label="Past run: x", content="z", answer_overlap=0.9),
    ]))
    save_trace(trace, dir=tmp_path)
    assert recall("who broke checkout?", dir=tmp_path)[0].used == ["PR #412"]


def test_capture_rejects_a_mistyped_outcome(tmp_path):
    with pytest.raises(ValueError):
        capture(LangGraphTracer(), query="q", answer="a", dir=tmp_path, outcome="succes")


def test_outcome_survives_to_the_saved_trace():
    assert to_tracestate(AgentTrace(query="q", outcome="failure"))["outcome"] == "failure"


def test_retriever_makes_episodes_visible_in_the_trace(tmp_path):
    save(tmp_path, "a.json", "who broke checkout?", answer="PR 412 did")
    tracer = LangGraphTracer()
    docs = EpisodeRetriever(dir=str(tmp_path)).invoke(
        "who broke checkout?", config={"callbacks": [tracer]}
    )
    assert isinstance(docs[0], Document)
    item = tracer.finish(answer="PR 412 did").retrievals[0].items[0]
    assert item.label == "Past run: who broke checkout?"
    assert item.answer_overlap > 0


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
