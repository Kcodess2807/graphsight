"""Does writing facts into the graph help later answers? Statements first, then
questions, under three setups that share the same agent, model and prompt:

  none          the graph only
  episodic      past statements recalled as episodes, by word overlap
  graph_memory  facts extracted from each statement and written into the graph

    python eval/run_memory.py --db eval/click.lbug --label memory-first-run
    python eval/run_memory.py --tasks memory_pytest --db eval/pytest.lbug --label memory-pytest

The graph file is copied, never written in place.
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
import tempfile
from collections import defaultdict
from math import comb
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "scripts"))

from graphsight_langgraph import LangGraphTracer  # noqa: E402

from episodic_agent import PROMPT, build_agent  # noqa: E402
from eval.grade import grade, normalize  # noqa: E402
from eval.run import FORMAT, K, records  # noqa: E402
from graphsight_memory import config  # noqa: E402
from graphsight_memory.db import TraceDB  # noqa: E402
from graphsight_memory.integrations.langchain import TraceRAGRetriever  # noqa: E402
from graphsight_memory.llm import make_client  # noqa: E402
from graphsight_memory.memory import AgentMemory  # noqa: E402
from graphsight_memory.router import TraceRouter  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tasks", default="memory_click", help="name in eval/tasks/")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--corpus", help="name in eval/corpus/; adds a full-context arm as the ceiling")
    args = parser.parse_args()
    logging.disable(logging.WARNING)

    tasks = json.loads((HERE / f"tasks/{args.tasks}.json").read_text(encoding="utf-8"))["tasks"]
    work = Path(tempfile.mkdtemp(prefix="graphsight-memeval-"))
    shutil.copy(args.db, work / "graph.lbug")
    db = TraceDB(work / "graph.lbug")
    router = TraceRouter(db)
    router.warm()
    llm = make_client()
    model = config.OPENROUTER_MODEL
    retriever = TraceRAGRetriever(router=router, k=K)

    # statements in order: every first statement, then every follow-up, as sessions would arrive
    rounds = max(len(t["statements"]) for t in tasks)
    statements = [(t["id"], t["statements"][i]) for i in range(rounds) for t in tasks if i < len(t["statements"])]

    episodes = work / "episodes"
    episodes.mkdir()
    for n, (task_id, text) in enumerate(statements):
        # a statement as a remembered run: what was said, so recall can return it
        (episodes / f"{n:03d}.json").write_text(json.dumps({
            "query": text, "answer": text, "outcome": "success",
            "computedAt": f"2026-11-13T00:00:{n:02d}Z", "graph": {"nodes": [], "edges": []},
        }), encoding="utf-8")

    def ask(question: str, use_memory: bool) -> tuple[str, int]:
        agent = build_agent(retriever, str(episodes), use_memory, llm, FORMAT)
        result = agent.invoke({"question": question}, config={"callbacks": [LangGraphTracer()]})
        return result["answer"], len(result["episodes"])

    rows: list[dict] = []

    def record(task: dict, condition: str, answer: str, **extra) -> None:
        graded = grade(answer, task["gold"])
        stale = {normalize(s) for s in task.get("stale", [])} & set(graded["got"] or [])
        rows.append({"task": task["id"], "category": task["category"], "condition": condition,
                     "question": task["question"], "gold": task["gold"], **graded,
                     "stale": bool(stale), "answer": answer, **extra})

    if args.corpus:
        # the ceiling: every record and every statement in the prompt, no retrieval at all
        corpus = json.loads((HERE / f"corpus/{args.corpus}.json").read_text(encoding="utf-8"))
        everything = ("\n\n".join(records(corpus)) + "\n\nWhat the team said, oldest first:\n"
                      + "\n".join(text for _, text in statements))
        for task in tasks:
            prompt = PROMPT.format(question=task["question"], episodes="(none)", evidence=everything) + FORMAT
            resp = llm.chat.completions.create(
                model=model, temperature=0, messages=[{"role": "user", "content": prompt}])
            record(task, "full_context", resp.choices[0].message.content or "")
        print("full_context: done", flush=True)

    # the graph is still clean here, so these two can't see graph memory
    for task in tasks:
        record(task, "none", ask(task["question"], False)[0])
        answer, recalled = ask(task["question"], True)
        record(task, "episodic", answer, recalled=recalled)
    print("none, episodic: done", flush=True)

    memory = AgentMemory(db, router.embed_query)
    learned = []
    for n, (task_id, text) in enumerate(statements):
        stored = memory.learn(text, llm, model, source=f"statement-{n}")
        learned.append({"task": task_id, "statement": text, "stored": stored})
    for task in tasks:
        record(task, "graph_memory", ask(task["question"], False)[0])
    print("graph_memory: done", flush=True)
    db.close()
    shutil.rmtree(work, ignore_errors=True)

    out = HERE / "results"
    (out / f"{args.label}.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    (out / f"{args.label}.learned.json").write_text(json.dumps(learned, indent=1), encoding="utf-8")
    summary = summarize(rows, learned, model)
    (out / f"{args.label}.md").write_text(summary, encoding="utf-8")
    print(summary)
    return 0


def summarize(rows: list[dict], learned: list[dict], model: str) -> str:
    table = defaultdict(list)
    for r in rows:
        table[r["condition"], r["category"]].append(r)
        table[r["condition"], "all"].append(r)
    cats = list(dict.fromkeys(r["category"] for r in rows)) + ["all"]
    setups = list(dict.fromkeys(r["condition"] for r in rows))

    def cell(c, k):
        got = table[c, k]
        return f"{sum(r['correct'] for r in got)}/{len(got)}"

    lines = [f"Model: `{model}`. Correct means the exact answer set.\n",
             "| Setup | " + " | ".join(cats) + " | stale answers on changed facts |",
             "|---|" + "---|" * (len(cats) + 1)]
    for c in setups:
        changed = table[c, "update"] + table[c, "retracted"] + table[c, "join_after_update"]
        stale = sum(r["stale"] for r in changed)
        lines.append(f"| {c} | " + " | ".join(cell(c, k) for k in cats) + f" | {stale}/{len(changed)} |")
    facts = sum(len(x["stored"]) for x in learned)
    empty = sum(not x["stored"] for x in learned)
    lines.append(f"\nExtraction stored {facts} facts from {len(learned)} statements; {empty} statements stored nothing.")
    lines.append(paired(rows, "graph_memory", "episodic"))
    return "\n".join(lines) + "\n"


def paired(rows: list[dict], a: str, b: str) -> str:
    """Sign test on the tasks where a real join exists. join_missing asks for
    'unknown', which tests abstaining, not joining, so it is left out here."""
    right = {(r["task"], r["condition"]): r["correct"] for r in rows if r["category"] != "join_missing"}
    ids = {t for t, _ in right}
    a_only = sum(right[t, a] and not right[t, b] for t in ids)
    b_only = sum(right[t, b] and not right[t, a] for t in ids)
    n, k = a_only + b_only, max(a_only, b_only)
    p = min(1.0, 2 * sum(comb(n, i) for i in range(k, n + 1)) / 2 ** n) if n else 1.0
    return (f"\n{a} vs {b}, {len(ids)} tasks: {a} alone right on {a_only}, {b} alone on {b_only}, "
            f"two-sided sign test p={p:.3f}.")


if __name__ == "__main__":
    raise SystemExit(main())
