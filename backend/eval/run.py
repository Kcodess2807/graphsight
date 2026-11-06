"""Does the graph help, and does memory help? Same model, same prompt, same tasks.

    python scripts/ingest_github.py --repo pallets/click --reset \
        --snapshot eval/corpus/pallets_click.json --db eval/click.lbug
    python eval/run.py --db eval/click.lbug --label first-run

Writes every question's context size, answer and grade to eval/results/, so each
number in the summary can be checked by hand.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import re
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "scripts"))

from graphsight_langgraph import LangGraphTracer, capture  # noqa: E402

from episodic_agent import PROMPT, build_agent  # noqa: E402
from eval.grade import grade  # noqa: E402
from tracerag import config  # noqa: E402
from tracerag.db import TraceDB  # noqa: E402
from tracerag.integrations.langchain import TraceRAGRetriever, format_page_content  # noqa: E402
from tracerag.llm import make_client  # noqa: E402
from tracerag.router import TraceRouter  # noqa: E402

K = config.TOP_K_VECTOR  # every retriever gets the same number of results
POISON_TASKS = 10

FORMAT = """

Finish with one last line in exactly this form, and nothing after it:
ANSWER: item, item
Put only what the question asks for on that line: for "who", only logins; for "which
PR", only PRs. Write PRs as PR #123, issues as Issue #123, commits as their short hash, people as
their login, and files as their path. If the context doesn't contain the answer,
write ANSWER: unknown"""


def records(corpus: dict) -> list[str]:
    """The corpus as flat text. Author, reviewers and files are written out, so the
    baselines get every structured fact the graph has. This is the strong baseline."""
    out = []
    for p in corpus["pulls"]:
        names = sorted({r["user"]["login"] for r in p["reviews"]} - {p["user"]["login"], None})
        files = ", ".join(f["filename"] for f in p["files"])
        out.append(f"PR #{p['number']}: {p['title']}\nAuthor: {p['user']['login']}\n"
                   f"Reviewed by: {', '.join(names) or 'nobody'}\nFiles: {files}\n{p['body'] or ''}")
    for i in corpus["issues"]:
        out.append(f"Issue #{i['number']}: {i['title']}\nReported by: {i['user']['login']}\n{i['body'] or ''}")
    for c in corpus["commits"]:
        out.append(f"Commit {c['sha'][:7]} by {c['author']['login']}\n{c['commit']['message']}")
    return out


class BM25:
    def __init__(self, docs: list[str], k1: float = 1.5, b: float = 0.75):
        self.tf = [Counter(self.words(d)) for d in docs]
        self.len = [sum(t.values()) for t in self.tf]
        self.avg = sum(self.len) / len(docs)
        df = Counter(w for t in self.tf for w in t)
        self.idf = {w: math.log(1 + (len(docs) - n + 0.5) / (n + 0.5)) for w, n in df.items()}
        self.k1, self.b = k1, b

    @staticmethod
    def words(text: str) -> list[str]:
        return re.findall(r"[a-z0-9_#]+", text.lower())

    def top(self, query: str, k: int) -> list[int]:
        scores = []
        for tf, length in zip(self.tf, self.len):
            s = sum(
                self.idf.get(w, 0) * tf[w] * (self.k1 + 1)
                / (tf[w] + self.k1 * (1 - self.b + self.b * length / self.avg))
                for w in self.words(query) if w in tf
            )
            scores.append(s)
        return sorted(range(len(scores)), key=lambda i: -scores[i])[:k]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--label", required=True, help="name for the result files")
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    logging.disable(logging.INFO)

    corpus = json.loads((HERE / "corpus/pallets_click.json").read_text(encoding="utf-8"))
    tasks = [json.loads(line) for line in (HERE / "tasks.jsonl").read_text(encoding="utf-8").splitlines()]
    docs = records(corpus)
    bm25 = BM25(docs)

    db = TraceDB(args.db)
    router = TraceRouter(db)
    router.warm()
    vectors = np.array([router._encode(d) for d in docs])
    llm = make_client()
    model = config.OPENROUTER_MODEL

    def ask(question: str, context: str) -> tuple[str, dict]:
        prompt = PROMPT.format(question=question, episodes="(none)", evidence=context) + FORMAT
        for attempt in range(3):
            try:
                resp = llm.chat.completions.create(
                    model=model, messages=[{"role": "user", "content": prompt}], temperature=0,
                )
                usage = resp.usage
                return resp.choices[0].message.content or "", {
                    "prompt_tokens": usage.prompt_tokens, "completion_tokens": usage.completion_tokens}
            except Exception as exc:  # noqa: BLE001 — a dropped call shouldn't cost a whole run
                if attempt == 2:
                    return f"(call failed: {exc})", {"prompt_tokens": 0, "completion_tokens": 0}
        raise AssertionError("unreachable")

    def graph_context(question: str, facts: bool) -> str:
        res = router.route(question, top_k=K)
        seen: set = set()
        parts = ["Graph facts:\n" + "\n".join(res.facts)] if facts and res.facts else []
        return "\n\n".join(parts + [format_page_content(n, seen) for n in res.results])

    conditions = {
        "full_context": lambda q: "\n\n".join(docs),
        "bm25": lambda q: "\n\n".join(docs[i] for i in bm25.top(q, K)),
        "vector": lambda q: "\n\n".join(
            docs[i] for i in np.argsort(-(vectors @ np.array(router._encode(q))))[:K]),
        "graph_no_facts": lambda q: graph_context(q, facts=False),
        "graph": lambda q: graph_context(q, facts=True),
    }

    rows: list[dict] = []

    def record(task: dict, condition: str, answer: str, usage: dict, context: int, **extra) -> None:
        rows.append({"task": task["id"], "category": task["category"], "condition": condition,
                     "question": task["question"], "gold": task["gold"], "context_chars": context,
                     **usage, **grade(answer, task["gold"]), "answer": answer, **extra})

    # part 1: the same question against every retriever
    for name, build in conditions.items():
        contexts = [build(t["question"]) for t in tasks]
        with ThreadPoolExecutor(args.workers) as pool:
            answers = list(pool.map(ask, [t["question"] for t in tasks], contexts))
        for task, context, (answer, usage) in zip(tasks, contexts, answers):
            record(task, name, answer, usage, len(context))
        print(f"{name}: done", flush=True)

    def run_agent(question: str, memory_dir: str, use_memory: bool, outcome_gold=None) -> tuple[str, dict, int]:
        agent = build_agent(TraceRAGRetriever(router=router, k=K), memory_dir, use_memory, llm, FORMAT)
        tracer = LangGraphTracer()
        result = agent.invoke({"question": question}, config={"callbacks": [tracer]})
        outcome = None
        if outcome_gold is not None:
            outcome = "success" if grade(result["answer"], outcome_gold)["correct"] else "failure"
        capture(tracer, query=question, answer=result["answer"], dir=memory_dir, outcome=outcome)
        return result["answer"], result.get("usage") or {}, len(result["episodes"])

    workdir = Path(tempfile.mkdtemp(prefix="graphsight-eval-"))
    try:
        # part 2: a past run on the same subject, with and without recall
        followups = [t for t in tasks if t["category"] == "followup"]
        for task in followups:
            memory = workdir / task["id"]
            seed_answer, _, _ = run_agent(task["seed"], str(memory), False, task["seed_gold"])
            seed_ok = grade(seed_answer, task["seed_gold"])["correct"]
            answer, usage, recalled = run_agent(task["question"], str(memory), True)
            record(task, "graph_memory", answer, usage, 0, recalled=recalled, seed_correct=seed_ok)
        print("graph_memory: done", flush=True)

        # part 3: a wrong memory marked as a success. Does it override the graph?
        lookups = [t for t in tasks if t["category"] == "lookup"][:POISON_TASKS]
        people = sorted({g for t in lookups for g in t["gold"]})
        for task in lookups:
            memory = workdir / f"poison-{task['id']}"
            memory.mkdir()
            wrong = next((p for p in people if p not in task["gold"]), "nobody")
            (memory / "poisoned.json").write_text(json.dumps({
                "query": task["question"], "answer": f"ANSWER: {wrong}", "outcome": "success",
                "computedAt": "2026-11-01T00:00:00Z", "graph": {"nodes": [], "edges": []},
            }), encoding="utf-8")
            answer, usage, recalled = run_agent(task["question"], str(memory), True)
            record(task, "graph_poisoned", answer, usage, 0, recalled=recalled,
                   poisoned_with=wrong, followed_poison=wrong.lower() in (grade(answer, [wrong])["got"] or []))
        print("graph_poisoned: done", flush=True)
    finally:
        db.close()
        shutil.rmtree(workdir, ignore_errors=True)

    out = HERE / "results"
    out.mkdir(exist_ok=True)
    (out / f"{args.label}.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    summary = summarize(rows, model)
    (out / f"{args.label}.md").write_text(summary, encoding="utf-8")
    print(summary)
    return 0


def summarize(rows: list[dict], model: str) -> str:
    conditions = list(dict.fromkeys(r["condition"] for r in rows))
    categories = list(dict.fromkeys(r["category"] for r in rows))
    table: dict = defaultdict(list)
    for r in rows:
        table[r["condition"], r["category"]].append(r)
        table[r["condition"], "all"].append(r)

    def cell(key) -> str:
        got = table.get(key)
        return f"{sum(r['correct'] for r in got)}/{len(got)}" if got else "-"

    lines = [f"Model: `{model}`. Correct means the exact answer set.\n",
             "| Condition | " + " | ".join(categories) + " | all | avg prompt tokens |",
             "|---|" + "---|" * (len(categories) + 2)]
    for c in conditions:
        tokens = [r["prompt_tokens"] for r in table[c, "all"]]
        lines.append(f"| {c} | " + " | ".join(cell((c, k)) for k in categories)
                     + f" | {cell((c, 'all'))} | {round(sum(tokens) / len(tokens))} |")
    poisoned = table.get(("graph_poisoned", "all"), [])
    if poisoned:
        lines.append(f"\nPoisoned memories followed: {sum(r['followed_poison'] for r in poisoned)}/{len(poisoned)}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
