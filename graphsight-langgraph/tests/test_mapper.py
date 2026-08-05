"""Mapper contract tests: AgentTrace -> TraceState shape the viewer renders."""
import pytest

from graphsight_langgraph import AgentTrace, Retrieval, RetrievedItem, Span, TraceEdge
from graphsight_langgraph.mapper import to_tracestate


def make_trace(overlaps=(0.5, 0.05), answer="an answer") -> AgentTrace:
    items = [
        RetrievedItem(id="pr_1", label="PR #1", kind="pull_request",
                      score=0.9, content="x", answer_overlap=overlaps[0]),
        RetrievedItem(id="c_1", label="abc123", kind="commit",
                      score=0.4, content="y", answer_overlap=overlaps[1]),
    ]
    edges = [TraceEdge(source="pr_1", target="c_1", relation="TOUCHES", weight=0.8),
             TraceEdge(source="pr_1", target="ghost", relation="TOUCHES")]
    return AgentTrace(
        query="q",
        spans=[Span(id="s1", name="retrieve", kind="node", start_ms=0.0, end_ms=1.5, status="ok")],
        retrievals=[Retrieval(span_id="s1", query="q", arm="graph", items=items, edges=edges)],
        answer=answer,
        latency_ms=1.5,
    )


def test_contract_top_level_keys():
    state = to_tracestate(make_trace())
    for key in ("id", "query", "computedAt", "weights", "confidence", "steps", "metrics", "graph"):
        assert key in state
    assert state["weights"]["intent"] == "relational"


def test_kind_normalization():
    state = to_tracestate(make_trace())
    types = {n["id"]: n["type"] for n in state["graph"]["nodes"]}
    assert types == {"pr_1": "PR", "c_1": "Commit"}
    unknown = to_tracestate(AgentTrace(query="q", retrievals=[
        Retrieval(span_id="s", query="q", items=[RetrievedItem(id="z", label="z", kind="weird")])
    ]))
    assert unknown["graph"]["nodes"][0]["type"] == "Document"


def test_retrieved_vs_used_active_flags():
    state = to_tracestate(make_trace(overlaps=(0.5, 0.05)))
    active = {n["id"]: n["active"] for n in state["graph"]["nodes"]}
    assert active == {"pr_1": True, "c_1": False}  # 0.05 < threshold -> dimmed
    # the label must describe the measurement, not assert the item went unused
    subtitles = {n["id"]: n["meta"]["subtitle"] for n in state["graph"]["nodes"]}
    assert "no lexical trace" in subtitles["c_1"]
    assert "overlaps the answer" in subtitles["pr_1"]
    assert "unused" not in subtitles["c_1"]


def test_no_answer_means_no_usage_claims():
    trace = make_trace(answer=None)
    for r in trace.retrievals:
        for i in r.items:
            i.answer_overlap = None
    state = to_tracestate(trace)
    assert all(n["active"] for n in state["graph"]["nodes"])


def test_edges_dropped_unless_both_endpoints_retrieved():
    state = to_tracestate(make_trace())
    edge_pairs = [(e["source"], e["target"]) for e in state["graph"]["edges"]]
    assert ("pr_1", "ghost") not in edge_pairs
    assert ("pr_1", "c_1") in edge_pairs


def test_edge_active_follows_node_usage():
    state = to_tracestate(make_trace(overlaps=(0.5, 0.05)))
    edge = state["graph"]["edges"][0]
    assert edge["active"] is False  # c_1 is unused, so the edge dims too


def test_vector_only_trace_is_conceptual():
    trace = make_trace()
    trace.retrievals[0].edges = []
    state = to_tracestate(trace)
    assert state["weights"] == {"vector": 1.0, "graph": 0.0, "intent": "conceptual"}


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
