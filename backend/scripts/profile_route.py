"""Profile TraceRouter.route() latency phase-by-phase.

Runs the SAME route() the /api/trace endpoint uses, but in a controlled loop
with the embedder pre-warmed, so the per-phase timings reflect steady state.
The router logs a "route timings (ms): ..." line per query.

    python scripts/profile_route.py --db graphs/pallets__flask.lbug
    python scripts/profile_route.py --db graphs/pydantic__pydantic.lbug -q "what changed in validation"

NOTE: LadybugDB is single-writer. If the uvicorn server is currently serving the
SAME .lbug file, this will fail to open it — point --db at a different graph, or
stop the server.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tracerag.db import TraceDB           # noqa: E402
from tracerag.router import TraceRouter   # noqa: E402

# A mix on purpose: "who…" short-circuits to relational (no intent LLM), while
# the keyword-less ones exercise the OpenRouter intent call — so you can see
# both the LLM-bearing and LLM-free phase costs.
DEFAULT_QUERIES = [
    "who reviewed the async changes",        # relational marker -> no intent LLM
    "what did the maintainers work on",      # keyword-less -> intent LLM fires
    "explain the recent changes",            # semantic marker -> no intent LLM
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Profile route() latency per phase.")
    p.add_argument("--db", type=Path, default=Path("graphs/pallets__flask.lbug"))
    p.add_argument("-q", "--query", action="append",
                   help="Query to run (repeatable). Defaults to a built-in mix.")
    p.add_argument("--top-k", type=int, default=10)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for noisy in ("httpx", "httpcore", "openai", "sentence_transformers",
                  "numexpr.utils", "gliner", "sentence_transformers.SentenceTransformer"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    try:
        db = TraceDB(args.db)
    except Exception as exc:  # noqa: BLE001
        print(f"[profile] could not open {args.db}: {exc}")
        print("[profile] is the uvicorn server serving this same graph? "
              "Point --db at a different graphs/*.lbug or stop the server.")
        return 1

    router = TraceRouter(db)
    print(f"[profile] db={args.db}  nodes={db.count_nodes()}")
    print("[profile] warming embedder (one-time model load)...")
    t = time.perf_counter()
    router.embed_query("warmup")
    print(f"[profile] embedder warm in {(time.perf_counter() - t) * 1000:.0f} ms\n")

    queries = args.query or DEFAULT_QUERIES
    try:
        for q in queries:
            t = time.perf_counter()
            resp = router.route(q, top_k=args.top_k)
            wall = (time.perf_counter() - t) * 1000
            print(f"  >> '{q}'  wall={wall:.0f} ms, {len(resp.results)} results\n")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
