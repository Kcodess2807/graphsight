"""Burst test that verifies the slowapi per-user rate limit on /api/answer.

Unlike scripts/stress_test.py (which THROTTLES with a semaphore to measure
graceful degradation), this script does the opposite: it fires every request at
the *same instant* -- a thundering herd -- to prove the limiter admits exactly N
and blocks the rest in a single fixed window.

    Expected for --burst 25 --limit 10:  10 x HTTP 200  +  15 x HTTP 429

------------------------------------------------------------------------------
HOW TO RUN
------------------------------------------------------------------------------
1. The server MUST run single-worker (uvicorn's default). slowapi's in-memory
   counter is per-process; with --workers N the burst is split across N
   independent buckets and far more than `limit` requests pass. So:

       uvicorn api:app --port 8000            # (no --workers flag)

2. Mode B -- dev-bypass (DEFAULT, for CI): leave CLERK_ISSUER unset on the
   server. Every request maps to the synthetic 'dev-user', so all 25 share one
   bucket. No token needed:

       python scripts/ratelimit_test.py

3. Mode A -- real Clerk JWT (manual end-to-end check): grab a fresh session
   token from the browser (it's short-lived, ~60s) and pass it:

       python scripts/ratelimit_test.py --token "eyJhbGci..."
"""

from __future__ import annotations

import argparse
import asyncio
import time
from collections import Counter

import aiohttp


async def _fire(
    session: aiohttp.ClientSession,
    url: str,
    payload: dict,
    timeout: float,
    start_gun: asyncio.Event,
    idx: int,
) -> dict:
    """One request that waits at the barrier, then fires the instant it opens.

    The `await start_gun.wait()` is the concurrency barrier: every worker parks
    here until the main coroutine fires the starting gun, so all `burst` requests
    leave the line on the SAME event-loop tick instead of trickling out as each
    task gets scheduled. That true simultaneity is what makes this a real burst
    test of the fixed window (a semaphore would serialize them and hide the seam).
    """
    await start_gun.wait()
    t0 = time.perf_counter()
    try:
        # NOTE: aiohttp does NOT raise on 4xx/5xx unless raise_for_status=True,
        # which we deliberately omit -- a 429 is the EXPECTED result here, not an
        # error. We just read the status code off the response.
        async with session.post(url, json=payload, timeout=timeout) as resp:
            await resp.read()  # drain the body so the connection is freed
            return {"idx": idx, "status": resp.status,
                    "latency": time.perf_counter() - t0}
    except asyncio.TimeoutError:
        # graceful: a slow/blocked request becomes a recorded outcome, not a crash
        return {"idx": idx, "status": "timeout",
                "latency": time.perf_counter() - t0}
    except aiohttp.ClientError as exc:
        return {"idx": idx, "status": f"error:{type(exc).__name__}",
                "latency": time.perf_counter() - t0}


async def run(url: str, token: str | None, burst: int, limit: int,
              timeout: float) -> bool:
    """Fire `burst` simultaneous requests; return True if the limit held exactly."""
    # --- identity: one token (or dev-bypass) => one rate-limit bucket ---
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        mode = "Mode A -- real Clerk JWT (--token)"
    else:
        # No header -> server runs every request as the synthetic 'dev-user',
        # so the whole burst still shares ONE bucket. Perfect for CI.
        mode = "Mode B -- dev-bypass (synthetic 'dev-user', no token)"

    # Empty context deliberately: /api/answer returns 200 instantly for empty
    # context WITHOUT calling the LLM. The rate-limit decorator runs BEFORE the
    # endpoint body, so the 429s still fire -- we prove the limiter for zero LLM
    # cost. (Set a real context only if you want to exercise the answer path.)
    payload = {"query": "rate-limit burst probe", "context": ""}

    expected_pass = limit
    expected_block = burst - limit

    print(f"Bursting {burst} simultaneous requests at {url}")
    print(f"  {mode}")
    print(f"  expecting {expected_pass} x 200 and {expected_block} x 429\n")
    print("  [!] Server MUST be single-worker (uvicorn default, NO --workers N)")
    print("      - slowapi's in-memory bucket is per-process; multiple workers")
    print("      mean multiple buckets and more than `limit` requests pass.\n")

    start_gun = asyncio.Event()

    async with aiohttp.ClientSession(headers=headers) as session:
        # Create all tasks first. Each immediately parks on `start_gun.wait()`.
        tasks = [
            asyncio.create_task(_fire(session, url, payload, timeout, start_gun, i))
            for i in range(burst)
        ]
        # Yield control so EVERY task gets scheduled and reaches the barrier
        # before we fire. Without this beat, set() could race ahead of tasks
        # that haven't hit `await start_gun.wait()` yet.
        await asyncio.sleep(0.1)

        wall_start = time.perf_counter()
        start_gun.set()                      # FIRE: all `burst` requests go now
        results = await asyncio.gather(*tasks)
        wall = time.perf_counter() - wall_start

    # --- tally outcomes ---
    statuses = Counter(r["status"] for r in results)
    n_200 = statuses.get(200, 0)
    n_429 = statuses.get(429, 0)
    lat = sorted(r["latency"] for r in results)

    print("=" * 60)
    print(f"{'Status / outcome':<28}{'count':>10}")
    print("-" * 60)
    for status, n in sorted(statuses.items(), key=lambda kv: str(kv[0])):
        print(f"{str(status):<28}{n:>10}")
    print("-" * 60)
    print(f"wall time            {wall:>8.3f}s")
    print(f"200 (admitted)       {n_200:>8} / expected {expected_pass}")
    print(f"429 (blocked)        {n_429:>8} / expected {expected_block}")
    if lat:
        print(f"latency min/max      {lat[0]:.3f} / {lat[-1]:.3f} s")
    print("=" * 60)

    # --- verdict ---
    passed = (n_200 == expected_pass and n_429 == expected_block)
    if passed:
        print(f"\n[PASS] Limiter held exactly: {expected_pass}x200, "
              f"{expected_block}x429. The 429 path is working.")
        return True

    print("\n[FAIL] Counts did not match. Likely causes, in order:")
    # Diagnostics ranked by how often each is the real culprit.
    if n_200 > expected_pass:
        print(f"  - {n_200} passed (> {expected_pass}). Either the server is "
              f"running MULTIPLE WORKERS (each with its own in-memory bucket),")
        print(f"    or -- far less likely at this speed -- the burst straddled a "
              f"60s fixed-window boundary. Re-run; if it persists it's workers.")
    if any(str(s).startswith(("error", "timeout")) for s in statuses):
        print("  - Hard failures (timeout/conn-error) present -- is the server up "
              "at this URL, and is the timeout high enough?")
    if n_200 == 0 and n_429 == 0:
        print("  - Nothing got through at all -- check the URL and that the API "
              "is actually listening.")
    if n_429 == 0 and n_200 < burst:
        print("  - No 429s seen -- is slowapi actually wired (app.state.limiter + "
              "@limiter.limit on /api/answer)?")
    return False


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Verify the per-user rate limit on /api/answer.")
    p.add_argument("--url", default="http://127.0.0.1:8000/api/answer")
    p.add_argument("--token", default=None,
                   help="Clerk JWT for Mode A; omit for Mode B dev-bypass.")
    p.add_argument("--burst", type=int, default=25,
                   help="total simultaneous requests (default 25)")
    p.add_argument("--limit", type=int, default=10,
                   help="the server's per-minute cap, i.e. expected 200s (default 10)")
    p.add_argument("--timeout", type=float, default=30.0)
    args = p.parse_args(argv)

    ok = asyncio.run(run(args.url, args.token, args.burst, args.limit, args.timeout))
    # exit code 0 on PASS, 1 on FAIL -- so CI (GitHub Actions) fails the job loudly.
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
