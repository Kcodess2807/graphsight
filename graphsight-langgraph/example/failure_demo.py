"""The failure case: an agent answers wrong, the trace shows why.
Offline, no API keys. Writes example/out_failure/{agent_trace,trace_state}.json."""
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
from graphsight_langgraph import LangGraphTracer, save_trace, to_tracestate  # noqa: E402

# The trap: an old PR that *talks* like the query scores high; the real
# culprit is a deps-only bump whose text shares almost nothing with it.
CORPUS = [
    Document(
        page_content=(
            "PR #4102 'fix: checkout payment failures under load — add retry "
            "with timeout' merged 8 months ago by Marco T. Added retry logic "
            "to the checkout-service payment authorizer."
        ),
        metadata={
            "id": "pr_4102",
            "label": "PR #4102",
            "kind": "pull_request",
            "score": 0.91,  # wordy overlap with the query — the trap
            "source": "https://github.com/acme/platform/pull/4102",
            "edges": [
                {"source": "pr_4102", "target": "svc_payment", "relation": "TOUCHES", "weight": 0.8},
            ],
        },
    ),
    Document(
        page_content=(
            "INC-2291 (sev1, open): checkout payment auth declining ~100% "
            "since the 2026-07-24 deploy. Rollback restores service."
        ),
        metadata={
            "id": "tkt_2291",
            "label": "INC-2291",
            "kind": "ticket",
            "score": 0.78,
            "source": "https://acme.atlassian.net/browse/INC-2291",
            "edges": [
                {"source": "tkt_2291", "target": "svc_payment", "relation": "REPORTS_ON", "weight": 0.9},
            ],
        },
    ),
    Document(
        page_content=(
            "payment-service: authorizes and captures card payments for "
            "checkout. Depends on stripe-sdk. Owned by payments team."
        ),
        metadata={
            "id": "svc_payment",
            "label": "payment-service",
            "kind": "service",
            "score": 0.55,
        },
    ),
    Document(
        page_content=(
            "PR #4977 'chore: bump stripe-sdk 11.2 -> 12.0' merged 2026-07-24 "
            "by Lena K. Dependency update only. Release notes: v12 removes "
            "the legacy auth_flow flag."
        ),
        metadata={
            "id": "pr_4977",
            "label": "PR #4977",
            "kind": "pull_request",
            "score": 0.34,  # the actual cause — near-zero word overlap
            "source": "https://github.com/acme/platform/pull/4977",
            "edges": [
                {"source": "pr_4977", "target": "svc_payment", "relation": "TOUCHES", "weight": 0.95},
                {"source": "person_lena", "target": "pr_4977", "relation": "AUTHORED", "weight": 0.9},
            ],
        },
    ),
    Document(
        page_content="Lena K., platform engineer. Handles dependency upgrades.",
        metadata={"id": "person_lena", "label": "Lena K.", "kind": "person", "score": 0.2},
    ),
]


class SimilarityRetriever(BaseRetriever):
    """Ranks purely by similarity score — like most vector RAG does."""

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        return sorted(CORPUS, key=lambda d: d.metadata["score"], reverse=True)


class AgentState(TypedDict):
    question: str
    docs: list[Document]
    answer: str


retriever = SimilarityRetriever()


def retrieve(state: AgentState, config: RunnableConfig) -> dict:
    docs = retriever.invoke(state["question"], config=config)
    return {"docs": docs}


def answer(state: AgentState, config: RunnableConfig) -> dict:
    # trusts the top-scored doc, like a grounded LLM would
    top = state["docs"][0]
    return {
        "answer": (
            f"The failures look like the timeout issue addressed in "
            f"{top.metadata['label']} — retry logic in the checkout payment "
            "authorizer. Consider re-applying that fix."
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

    question = "Why are checkout payments failing since yesterday's deploy?"

    tracer = LangGraphTracer()
    result = graph.invoke({"question": question}, config={"callbacks": [tracer]})
    trace = tracer.finish(query=question, answer=result["answer"])

    out = Path(__file__).parent / "out_failure"
    out.mkdir(exist_ok=True)
    (out / "agent_trace.json").write_text(
        json.dumps(trace.to_dict(), indent=2), encoding="utf-8"
    )
    (out / "trace_state.json").write_text(
        json.dumps(to_tracestate(trace), indent=2), encoding="utf-8"
    )
    save_trace(trace)  # also lands in ./.graphsight/ — browse with: graphsight .graphsight/

    print(f"question : {question}")
    print(f"answer   : {result['answer']}")
    print()
    print("that answer is WRONG — PR #4102 shipped 8 months ago.")
    print("the real cause is PR #4977 (stripe-sdk 12 bump, merged yesterday).")
    print()
    print("the trace shows why the agent got fooled:")
    for r in trace.retrievals:
        for item in r.items:
            marker = "  <- trap" if item.id == "pr_4102" else ("  <- actual cause" if item.id == "pr_4977" else "")
            print(f"  {item.label:16} score={item.score}{marker}")
    print()
    print("similarity ranked a wordy stale PR over a deps-only change whose")
    print("only link to the incident is the graph: INC-2291 -> payment-service <- PR #4977")
    print()
    print(f"see it: graphsight {out / 'trace_state.json'}")


if __name__ == "__main__":
    main()
