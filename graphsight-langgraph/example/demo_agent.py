"""Offline demo: a small LangGraph agent traced end to end, no API keys.
Writes example/out/{agent_trace,trace_state}.json."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TypedDict

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from graphsight_langgraph import LangGraphTracer, to_tracestate  # noqa: E402

# a tiny "codebase memory" corpus with scores + relational edges
CORPUS = [
    Document(
        page_content=(
            "PR #4821 'fix: idempotent refund path in checkout' merged by "
            "Priya N. Touches checkout-service payment handler; linked to "
            "JIRA-982 after the v2.4 regression."
        ),
        metadata={
            "id": "pr_4821",
            "label": "PR #4821",
            "kind": "pull_request",
            "score": 0.94,
            "source": "https://github.com/acme/platform/pull/4821",
            "edges": [
                {"source": "pr_4821", "target": "svc_checkout", "relation": "TOUCHES", "weight": 0.9},
                {"source": "person_priya", "target": "pr_4821", "relation": "AUTHORED", "weight": 0.95},
            ],
        },
    ),
    Document(
        page_content=(
            "checkout-service handles cart, payment authorization, and refunds. "
            "Owned by the payments team; failure spike began after release v2.4."
        ),
        metadata={
            "id": "svc_checkout",
            "label": "checkout-service",
            "kind": "service",
            "score": 0.88,
            "edges": [
                {"source": "tkt_982", "target": "svc_checkout", "relation": "REPORTS_ON", "weight": 0.8},
            ],
        },
    ),
    Document(
        page_content="Priya N., senior engineer on payments. Reviewer/author on recent checkout changes.",
        metadata={"id": "person_priya", "label": "Priya N.", "kind": "person", "score": 0.71},
    ),
    Document(
        page_content=(
            "JIRA-982: 'Refunds double-charging after v2.4'. High priority; "
            "resolved by PR #4821."
        ),
        metadata={
            "id": "tkt_982",
            "label": "JIRA-982",
            "kind": "ticket",
            "score": 0.83,
            "source": "https://acme.atlassian.net/browse/JIRA-982",
            "edges": [
                {"source": "pr_4821", "target": "tkt_982", "relation": "RESOLVES", "weight": 0.92},
            ],
        },
    ),
]


class CodebaseMemoryRetriever(BaseRetriever):
    """In-memory scored retriever standing in for any real vector/graph store."""

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        # a real retriever would rank here; the fixed scores play that role
        return sorted(CORPUS, key=lambda d: d.metadata["score"], reverse=True)


# the LangGraph agent: retrieve → answer
class AgentState(TypedDict):
    question: str
    docs: list[Document]
    answer: str


retriever = CodebaseMemoryRetriever()


def retrieve(state: AgentState, config: RunnableConfig) -> dict:
    # passing the node's config through is what lets callbacks (the tracer)
    # observe this retriever call
    docs = retriever.invoke(state["question"], config=config)
    return {"docs": docs}


def answer(state: AgentState, config: RunnableConfig) -> dict:
    # deterministic composition so the demo needs no LLM key; swap for a
    # model call in real use
    top = state["docs"][0]
    return {
        "answer": (
            f"The regression traces to {top.metadata['label']} in "
            "checkout-service, authored by Priya N. and resolving JIRA-982."
        )
    }


graph = (
    StateGraph(AgentState)
    .add_node("retrieve", retrieve)
    .add_node("answer", answer)
    .add_edge(START, "retrieve")
    .add_edge("retrieve", "answer")
    .add_edge("answer", END)
    .compile()
)


def main() -> None:
    # windows consoles default to cp1252
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass

    question = "Which PR caused the checkout regression, and who reviewed it?"

    tracer = LangGraphTracer()
    result = graph.invoke({"question": question}, config={"callbacks": [tracer]})
    trace = tracer.finish(query=question, answer=result["answer"])

    out = Path(__file__).parent / "out"
    out.mkdir(exist_ok=True)
    (out / "agent_trace.json").write_text(
        json.dumps(trace.to_dict(), indent=2), encoding="utf-8"
    )
    (out / "trace_state.json").write_text(
        json.dumps(to_tracestate(trace), indent=2), encoding="utf-8"
    )

    retrieved = sum(len(r.items) for r in trace.retrievals)
    edges = sum(len(r.edges) for r in trace.retrievals)
    print(f"answer   : {result['answer']}")
    print(f"spans    : {len(trace.spans)} ({', '.join(s.name for s in trace.spans)})")
    print(f"retrieved: {retrieved} items · {edges} edges · arm={trace.retrievals[0].arm}")
    print(f"latency  : {trace.latency_ms:.1f}ms")
    print(f"wrote    : {out / 'agent_trace.json'}")
    print(f"wrote    : {out / 'trace_state.json'}  ← paste into /memory/import")


if __name__ == "__main__":
    main()
