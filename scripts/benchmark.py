"""LLM-as-a-judge benchmark for the TraceRAG pipeline.

Runs a fixed set of semantic + relational queries through the TraceRouter,
asks a Groq cloud model whether the retrieved context is sufficient to answer
each query, and reports token usage + accuracy split by intent category.

    python -m scripts.benchmark --db memory.lbug --out results.csv
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tracerag import config                                  # noqa: E402
from tracerag.db import TraceDB                               # noqa: E402
from tracerag.router import RoutedNode, TraceRouter          # noqa: E402

logger = logging.getLogger("tracerag.benchmark")

# --- Groq free-tier rate-limit pacing (6,000 tokens/min) ------------------- #
# Judge requests must stay under the TPM cap. With JUDGE_CONTEXT_CHARS≈5000
# (~1,250 tokens/request) and one request every JUDGE_SLEEP_SEC=15s (4/min),
# that's ~5,000 TPM — safely under 6,000. (The originally-suggested 15k chars
# at 12s would be ~18,750 TPM and still trip the limit.)
JUDGE_CONTEXT_CHARS = 5000
JUDGE_SLEEP_SEC = 15


@dataclass(frozen=True)
class TestQuery:
    query: str
    category: str  # "semantic" | "relational"


TEST_SET: list[TestQuery] = [
    # --- Semantic / conceptual (lean on vectors) ---
    TestQuery("Explain the general MLOps system architecture.", "semantic"),
    TestQuery("Give an overview of the model deployment pipeline.", "semantic"),
    TestQuery("Describe the purpose of the model monitoring service.", "semantic"),
    TestQuery("What is the role of the feature store in the platform?", "semantic"),
    TestQuery("Summarize how the CI/CD process works for model releases.", "semantic"),
    # --- Relational / multi-hop (lean on graph) ---
    TestQuery("Which automation script triggered the deployment failure?", "relational"),
    TestQuery("Who owns the service that caused the latest outage?", "relational"),
    TestQuery("Which PR introduced the bug linked to ticket OPS-142?", "relational"),
    TestQuery("What service depends on the auth module that failed?", "relational"),
    TestQuery("Which team is responsible for the repo tied to the payment incident?", "relational"),
]


def approx_tokens(text: str) -> int:
    """Cheap token estimate: words * 1.3."""
    return int(len(text.split()) * 1.3)


def baseline_context(db: TraceDB, node_ids: list[str]) -> str:
    """Pure-vector control: concatenate the unique chunk texts mentioning the
    top-k vector hits (no graph focusing, no per-node snippet cap)."""
    docs_by_entity = db.documents_for_entities(node_ids)
    seen, parts = set(), []
    for nid in node_ids:
        for d in docs_by_entity.get(nid, []):
            text = (d.get("content") or "").strip()
            if text and text not in seen:
                seen.add(text)
                parts.append(text)
    return "\n\n".join(parts)


def hybrid_context(results: list[RoutedNode]) -> str:
    """Realistic hybrid context: entity framing + each entity's chunk text,
    but GLOBALLY deduped so a chunk mentioned by several top-k entities is
    counted once (not once per entity). This is the fix for hybrid tokens
    exceeding the baseline — the inflation was repeated chunks, not node count.
    """
    seen, parts = set(), []
    for node in results:  # already sliced to top_k by the router
        parts.append(f"Entity: {node.label or node.id} ({node.type or 'Unknown'})")
        for d in node.documents:
            text = (d.get("content") or "").strip()
            if text and text not in seen:
                seen.add(text)
                parts.append(text)
    return "\n\n".join(parts)


def _safe_vector_search(db: TraceDB, embedding: list[float], k: int) -> list[dict]:
    try:
        return db.vector_search(embedding, k=k)
    except Exception as exc:  # noqa: BLE001 — empty index, etc.
        logger.debug("baseline vector_search returned nothing (%s)", exc)
        return []


def judge_sufficient(client, query: str, context: str) -> tuple[int, str]:
    """LLM-as-judge: does the context suffice to answer the query? -> (1/0, raw)."""
    prompt = (
        f"Given this retrieved context, does it contain sufficient information "
        f"to answer the following query: '{query}'? Answer ONLY 'YES' or 'NO'.\n\n"
        f"Context:\n{context if context.strip() else '(no context retrieved)'}"
    )
    try:
        resp = client.chat.completions.create(
            model=config.GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        answer = resp.choices[0].message.content.strip().upper()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Judge LLM failed (%s); scoring as 0.", exc)
        return 0, f"ERROR: {exc}"
    return (1 if answer.startswith("YES") else 0), answer


def run(db_path: Path, out_path: Path, k: int) -> list[dict]:
    from groq import Groq

    db = TraceDB(db_path)
    db.init_schema()
    router = TraceRouter(db)
    client = Groq(api_key=config.GROQ_API_KEY)

    rows: list[dict] = []
    try:
        for tq in TEST_SET:
            # Hybrid (router) arm — globally deduped context.
            resp = router.route(tq.query, top_k=k)
            context = hybrid_context(resp.results)
            intent = resp.trace_log.get("intent", {})
            tokens = approx_tokens(context)

            # Pure-vector baseline (control) arm.
            embedding = router.embed_query(tq.query)
            baseline_ids = [h["id"] for h in _safe_vector_search(db, embedding, k)
                            if h.get("id")]
            baseline_tokens = approx_tokens(baseline_context(db, baseline_ids))
            reduction = (
                (1 - tokens / baseline_tokens) * 100 if baseline_tokens else 0.0
            )

            # Judge on a truncated copy to stay under Groq's per-request/TPM cap;
            # the token metric above still reflects the full retrieved context.
            verdict, raw = judge_sufficient(
                client, tq.query, context[:JUDGE_CONTEXT_CHARS]
            )
            time.sleep(JUDGE_SLEEP_SEC)  # pace requests under 6,000 TPM

            rows.append({
                "query": tq.query,
                "category": tq.category,
                "intent_type": intent.get("type"),
                "alpha": intent.get("alpha"),
                "beta": intent.get("beta"),
                "num_docs": len(resp.results),
                "context_tokens": tokens,
                "baseline_tokens": baseline_tokens,
                "token_reduction_pct": round(reduction, 1),
                "judge": verdict,
                "judge_raw": raw,
            })
            logger.info("[%-10s] judge=%d tokens=%4d baseline=%4d reduction=%5.1f%%  %s",
                        tq.category, verdict, tokens, baseline_tokens, reduction, tq.query)
    finally:
        db.close()

    _write_csv(rows, out_path)
    return rows


def _write_csv(rows: list[dict], out_path: Path) -> None:
    fields = ["query", "category", "intent_type", "alpha", "beta", "num_docs",
              "context_tokens", "baseline_tokens", "token_reduction_pct",
              "judge", "judge_raw"]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    logger.info("Wrote %d rows -> %s", len(rows), out_path)


def print_summary(rows: list[dict]) -> None:
    header = (f"{'Category':<12}{'Queries':>9}{'Hybrid Tok':>12}"
              f"{'Baseline Tok':>14}{'Reduction':>11}{'Accuracy':>11}")
    width = len(header)

    def line(label: str, group: list[dict]) -> None:
        n = len(group)
        if not n:
            return
        hyb = sum(r["context_tokens"] for r in group) / n
        base = sum(r["baseline_tokens"] for r in group) / n
        red = sum(r["token_reduction_pct"] for r in group) / n
        acc = sum(r["judge"] for r in group) / n
        print(f"{label:<12}{n:>9}{hyb:>12.1f}{base:>14.1f}{red:>10.1f}%{acc:>11.1%}")

    print("\n" + "=" * width)
    print(header)
    print("-" * width)
    for category in ("semantic", "relational"):
        line(category, [r for r in rows if r["category"] == category])
    print("-" * width)
    line("OVERALL", rows)
    print("=" * width + "\n")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="TraceRAG LLM-as-judge benchmark.")
    p.add_argument("--db", type=Path, default=config.DB_PATH)
    p.add_argument("--out", type=Path, default=config.RESULTS_CSV)
    p.add_argument("--k", type=int, default=config.TOP_K_VECTOR,
                   help="Top-k entities retrieved per query.")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(name)s  %(message)s",
    )
    for noisy in ("httpx", "httpcore", "groq", "sentence_transformers"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    rows = run(args.db, args.out, args.k)
    print_summary(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
