"""Load test for the TraceRAG API.

Start the API first (uvicorn api:app --port 8000), then:

    python scripts/stress_test.py --requests 200 --concurrency 25
"""

from __future__ import annotations

import argparse
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import requests

QUERIES = [
    "who reviewed the shell completion changes",
    "which PR fixed the flag value bug",
    "who authored the type hint PR",
    "which ticket is related to option parsing",
    "explain the architecture of click",
]


def _one(url: str, query: str, timeout: float) -> dict:
    start = time.perf_counter()
    try:
        status = requests.post(url, json={"query": query}, timeout=timeout).status_code
    except requests.Timeout:
        status = "timeout"
    except requests.RequestException as exc:
        status = f"error:{type(exc).__name__}"
    return {"status": status, "latency": time.perf_counter() - start}


def run(url: str, total: int, concurrency: int, timeout: float) -> None:
    print(f"Hammering {url}\n  {total} requests, concurrency={concurrency}, timeout={timeout}s\n")
    wall_start = time.perf_counter()
    with ThreadPoolExecutor(concurrency) as pool:
        results = list(pool.map(lambda i: _one(url, QUERIES[i % len(QUERIES)], timeout), range(total)))
    wall = time.perf_counter() - wall_start

    statuses = Counter(r["status"] for r in results)
    lat = sorted(r["latency"] for r in results)

    def pct(p: float) -> float:
        return lat[min(len(lat) - 1, int(len(lat) * p))] if lat else 0.0

    for status, n in sorted(statuses.items(), key=lambda kv: str(kv[0])):
        print(f"{str(status):<28}{n:>10}")
    print(f"wall time            {wall:>8.2f}s")
    print(f"throughput           {total / wall:>8.1f} req/s")
    print(f"success (200)        {statuses.get(200, 0):>8} / {total}")
    print(f"latency p50/p90/p99  {pct(.5):.3f} / {pct(.9):.3f} / {pct(.99):.3f} s")
    if any(str(s).startswith(("error", "timeout")) or s in (500, 502) for s in statuses):
        print("\n[!] Hard failures (5xx, timeouts or connection errors): check for crashes or DB locks.")
    if statuses.get(429) or statuses.get(503):
        print("\n[ok] The server shed load with 429/503 under pressure.")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="TraceRAG load test.")
    p.add_argument("--url", default="http://127.0.0.1:8000/api/trace")
    p.add_argument("--requests", type=int, default=100)
    p.add_argument("--concurrency", type=int, default=20)
    p.add_argument("--timeout", type=float, default=30.0)
    args = p.parse_args(argv)
    run(args.url, args.requests, args.concurrency, args.timeout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
