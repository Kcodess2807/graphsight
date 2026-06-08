"""Async load test for the TraceRAG FastAPI endpoint.

Start the API first (uvicorn api:app --port 8000), then:

    python scripts/stress_test.py --requests 200 --concurrency 25
"""

from __future__ import annotations

import argparse
import asyncio
import time
from collections import Counter

import aiohttp

QUERIES = [
    "What was incident INC-4471 about?",
    "What is the responsibility of the PaymentService?",
    "Who is the tech lead and owning team for PaymentService?",
    "What does payment-service depend on?",
    "How does the AuthLayer handle login and JWT issuance?",
    "Explain the ShopFlow commerce platform architecture.",
    "What is related to PR #847?",
    "Which component was affected in incident INC-4480?",
]


async def _one(session, url, query, sem, timeout) -> dict:
    async with sem:
        start = time.perf_counter()
        try:
            async with session.post(url, json={"query": query}, timeout=timeout) as resp:
                await resp.read()  # drain
                return {"status": resp.status, "latency": time.perf_counter() - start}
        except asyncio.TimeoutError:
            return {"status": "timeout", "latency": time.perf_counter() - start}
        except aiohttp.ClientError as exc:
            return {"status": f"error:{type(exc).__name__}", "latency": time.perf_counter() - start}


async def run(url: str, total: int, concurrency: int, timeout: float) -> None:
    sem = asyncio.Semaphore(concurrency)
    print(f"Hammering {url}\n  {total} requests, concurrency={concurrency}, "
          f"timeout={timeout}s\n")
    wall_start = time.perf_counter()
    async with aiohttp.ClientSession() as session:
        tasks = [
            _one(session, url, QUERIES[i % len(QUERIES)], sem, timeout)
            for i in range(total)
        ]
        results = await asyncio.gather(*tasks)
    wall = time.perf_counter() - wall_start

    statuses = Counter(r["status"] for r in results)
    ok = [r["latency"] for r in results if r["status"] == 200]
    lat = sorted(r["latency"] for r in results)

    def pct(p: float) -> float:
        return lat[min(len(lat) - 1, int(len(lat) * p))] if lat else 0.0

    print("=" * 60)
    print(f"{'Status / outcome':<28}{'count':>10}")
    print("-" * 60)
    for status, n in sorted(statuses.items(), key=lambda kv: str(kv[0])):
        print(f"{str(status):<28}{n:>10}")
    print("-" * 60)
    print(f"wall time            {wall:>8.2f}s")
    print(f"throughput           {total / wall:>8.1f} req/s")
    print(f"success (200)        {len(ok):>8} / {total}")
    print(f"latency p50/p90/p99  {pct(.5):.3f} / {pct(.9):.3f} / {pct(.99):.3f} s")
    print(f"latency max          {(lat[-1] if lat else 0):.3f} s")
    print("=" * 60)
    if any(str(s).startswith(("error", "timeout")) or s in (500, 502) for s in statuses):
        print("\n[!] Hard failures present (5xx/timeout/conn-error): the worker may "
              "not be degrading gracefully — check for crashes or DB read-locks.")
    if statuses.get(429) or statuses.get(503):
        print("\n[ok] Server shed load with 429/503 under pressure (graceful).")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="TraceRAG async load test.")
    p.add_argument("--url", default="http://127.0.0.1:8000/api/trace")
    p.add_argument("--requests", type=int, default=100)
    p.add_argument("--concurrency", type=int, default=20)
    p.add_argument("--timeout", type=float, default=30.0)
    args = p.parse_args(argv)
    asyncio.run(run(args.url, args.requests, args.concurrency, args.timeout))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
