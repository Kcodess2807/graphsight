"""Tracer integration tests against real langgraph, sync and async."""
import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from graphsight_langgraph import LangGraphTracer

CORPUS = [
    Document(
        page_content="PR #1 fixes the checkout timeout bug in payments",
        metadata={
            "id": "pr_1", "label": "PR #1", "kind": "pull_request", "score": 0.9,
            "edges": [
                {"source": "pr_1", "target": "svc_pay", "relation": "TOUCHES", "weight": 0.8},
                # duplicate on purpose — tracer must dedup
                {"source": "pr_1", "target": "svc_pay", "relation": "TOUCHES", "weight": 0.8},
            ],
        },
    ),
    Document(
        page_content="payment-service handles card auth",
        metadata={"id": "svc_pay", "label": "payment-service", "kind": "service"},  # no score
    ),
]


class FakeRetriever(BaseRetriever):
    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        return CORPUS


class State(TypedDict):
    question: str
    docs: list
    answer: str


def build_graph():
    retriever = FakeRetriever()

    def retrieve(state, config):
        return {"docs": retriever.invoke(state["question"], config=config)}

    def answer(state, config):
        return {"answer": "The checkout timeout traces to PR #1 in payments."}

    return (
        StateGraph(State)
        .add_node("retrieve", retrieve)
        .add_node("answer", answer)
        .add_edge(START, "retrieve")
        .add_edge("retrieve", "answer")
        .add_edge("answer", END)
        .compile()
    )


def run_sync():
    tracer = LangGraphTracer()
    result = build_graph().invoke(
        {"question": "why is checkout timing out?"}, config={"callbacks": [tracer]}
    )
    return tracer.finish(answer=result["answer"])


def test_spans_are_user_nodes_plus_retriever():
    trace = run_sync()
    names = [s.name for s in trace.spans]
    assert "retrieve" in names and "answer" in names
    # framework internals filtered out
    assert not any(n in ("LangGraph", "RunnableSequence", "ChannelWrite") for n in names)
    assert all(s.status == "ok" and s.end_ms is not None for s in trace.spans)


def test_retrieval_items_scores_edges_arm():
    trace = run_sync()
    assert len(trace.retrievals) == 1
    r = trace.retrievals[0]
    assert r.query == "why is checkout timing out?"
    assert [i.id for i in r.items] == ["pr_1", "svc_pay"]
    assert r.items[0].score == 0.9
    assert r.items[1].score is None  # absent stays None, never invented
    assert len(r.edges) == 1  # deduped
    assert r.arm == "graph"


def test_answer_overlap_and_query_fallback():
    trace = run_sync()
    r = trace.retrievals[0]
    assert trace.query == "why is checkout timing out?"  # from first retriever call
    assert r.items[0].answer_overlap is not None and r.items[0].answer_overlap > 0.2
    assert r.items[1].answer_overlap is not None  # computed for every item


def test_async_ainvoke_captures_the_same():
    tracer = LangGraphTracer()
    result = asyncio.run(
        build_graph().ainvoke(
            {"question": "why is checkout timing out?"}, config={"callbacks": [tracer]}
        )
    )
    trace = tracer.finish(answer=result["answer"])
    assert [s.name for s in trace.spans if s.kind == "node"] == ["retrieve", "answer"]
    assert len(trace.retrievals) == 1
    assert trace.retrievals[0].arm == "graph"
    assert trace.latency_ms is not None and trace.latency_ms > 0


def test_finish_defaults_answer_to_last_llm_generation():
    tracer = LangGraphTracer()
    fake = SimpleNamespace(generations=[[SimpleNamespace(text="generated answer text")]])
    run_id = uuid4()
    tracer.on_llm_start({}, ["prompt"], run_id=run_id)
    tracer.on_llm_end(fake, run_id=run_id)
    trace = tracer.finish(query="q")
    assert trace.answer == "generated answer text"


def test_finish_without_answer_leaves_overlap_none():
    tracer = LangGraphTracer()
    build_graph().invoke(
        {"question": "anything"}, config={"callbacks": [tracer]}
    )
    trace = tracer.finish()  # no answer anywhere
    assert all(i.answer_overlap is None for r in trace.retrievals for i in r.items)


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
