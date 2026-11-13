"""A real agent with episodic memory: recall past runs, retrieve from the graph, answer.

    python scripts/episodic_agent.py --db graphs/pallets__click.lbug \
        --expect "PR #" "who changed option parsing recently?"

Each run lands in .graphsight/. Runs that pass --expect are labelled success and
become recallable; run the same task again and the viewer shows the episode it
used: `graphsight .graphsight/`. --no-memory is the baseline to compare against.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TypedDict

from langchain_core.documents import Document
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from graphsight_langgraph import EpisodeRetriever, LangGraphTracer, capture  # noqa: E402

from tracerag import config as engine_config  # noqa: E402
from tracerag.db import TraceDB  # noqa: E402
from tracerag.integrations.langchain import TraceRAGRetriever  # noqa: E402
from tracerag.llm import make_client  # noqa: E402

PROMPT = """Answer the question from the context. Name the specific PRs, people, and files.
If the context does not contain the answer, say so plainly rather than guessing.

Past runs show what worked before, but they can be out of date. When a past run
disagrees with the graph evidence, trust the graph evidence.

Question: {question}

Past runs:
{episodes}

Graph evidence:
{evidence}"""


class State(TypedDict, total=False):
    question: str
    episodes: list[Document]
    evidence: list[Document]
    answer: str
    usage: dict


def build_agent(
    graph_retriever: TraceRAGRetriever, memory_dir: str, use_memory: bool, llm, suffix: str = ""
):
    episode_retriever = EpisodeRetriever(dir=memory_dir)

    def recall_node(state: State, config: RunnableConfig) -> State:
        if not use_memory:
            return {"episodes": []}
        return {"episodes": episode_retriever.invoke(state["question"], config=config)}

    def retrieve_node(state: State, config: RunnableConfig) -> State:
        # a recalled episode names entities the question didn't, so search with them too
        recalled = " ".join(d.page_content for d in state["episodes"])
        return {"evidence": graph_retriever.invoke(f"{state['question']} {recalled}".strip(), config=config)}

    def generate_node(state: State) -> State:
        prompt = PROMPT.format(
            question=state["question"],
            episodes="\n\n".join(d.page_content for d in state["episodes"]) or "(none)",
            evidence="\n\n".join(d.page_content for d in state["evidence"]) or "(none)",
        ) + suffix
        resp = llm.chat.completions.create(
            model=engine_config.OPENROUTER_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        return {
            "answer": (resp.choices[0].message.content or "").strip(),
            "usage": {"prompt_tokens": resp.usage.prompt_tokens,
                      "completion_tokens": resp.usage.completion_tokens},
        }

    graph = StateGraph(State)
    graph.add_node("recall", recall_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("generate", generate_node)
    graph.add_edge(START, "recall")
    graph.add_edge("recall", "retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)
    return graph.compile()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("question")
    parser.add_argument("--db", type=Path, default=engine_config.DB_PATH)
    parser.add_argument("--memory-dir", default=".graphsight")
    parser.add_argument("--expect", help="text a correct answer must contain; labels the run")
    parser.add_argument("--no-memory", action="store_true", help="skip recall (the baseline)")
    args = parser.parse_args()

    db = TraceDB(args.db)
    try:
        agent = build_agent(
            TraceRAGRetriever.from_db(db), args.memory_dir, not args.no_memory, make_client()
        )
        tracer = LangGraphTracer()
        result = agent.invoke({"question": args.question}, config={"callbacks": [tracer]})
    finally:
        db.close()

    outcome = None
    if args.expect:
        outcome = "success" if args.expect.lower() in result["answer"].lower() else "failure"
    path = capture(
        tracer, query=args.question, answer=result["answer"],
        dir=args.memory_dir, outcome=outcome,
    )

    print(result["answer"])
    print(f"\nrecalled {len(result['episodes'])} episode(s) · outcome: {outcome} · saved {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
