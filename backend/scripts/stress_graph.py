# -*- coding: utf-8 -*-
"""Direct stress test of the GraphRAG retrieval core against ONE graph.

Hammers TraceRouter.route() concurrently (no HTTP, no auth, no answer-LLM) with
a battery of valid + adversarial + fuzz queries to surface crashes, injection
issues, encoding bugs, latency outliers, thread-safety problems, and correctness
regressions on a new graph before it goes on camera.

    python scripts/stress_graph.py --db graphs/apache__kafka.lbug \
        --iterations 400 --concurrency 16

Hermetic: the intent-classifier LLM fallback is stubbed, so no billed calls and
no network — what's measured is purely vector + graph retrieval over the graph.
"""
from __future__ import annotations

import argparse
import sys
import time
import traceback
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tracerag import config                     # noqa: E402
from tracerag.db import TraceDB                  # noqa: E402
from tracerag.router import TraceRouter          # noqa: E402

# (label, query, category, expect_hits)
#   valid    -> must return results; we also spot-check correctness
#   offdomain-> should gracefully return few/none, never crash
#   fuzz     -> must NOT crash; result count irrelevant
BATTERY: list[tuple[str, str, str, bool]] = [
    # --- valid relational (the real demo questions) ---
    ("hero",        "What is related to KAFKA-20688?", "valid", True),
    ("ticket2",     "What is related to KAFKA-20570?", "valid", True),
    ("person1",     "What did Matthias J. Sax work on?", "valid", True),
    ("person2",     "What did Alieh Saeedi work on?", "valid", True),
    ("person_acc",  "What did José Armando García Sancio work on?", "valid", True),
    ("lib1",        "What is connected to Kafka Streams?", "valid", True),
    ("lib2",        "What is related to streams?", "valid", True),
    ("kip",         "What is KIP-1301 about?", "valid", True),
    # --- semantic (intent stubbed, exercises vector arm) ---
    ("sem1",        "Explain the recent RocksDB state-store changes.", "valid", True),
    ("sem2",        "How does Kafka handle exactly-once semantics?", "valid", True),
    # --- off-domain: should degrade gracefully ---
    ("off1",        "How does the payment gateway handle refunds?", "offdomain", False),
    ("off2",        "Best recipe for sourdough bread", "offdomain", False),
    ("off3",        "What is the capital of France?", "offdomain", False),
    # --- fuzz / adversarial: must not crash ---
    ("empty",       "", "fuzz", False),
    ("spaces",      "          ", "fuzz", False),
    ("one_char",    "a", "fuzz", False),
    ("digits",      "1234567890", "fuzz", False),
    ("emoji",       "🔥🔥 what is related to streams 🔥🔥", "fuzz", False),
    ("accents",     "Què està relacionat amb José Armando García Sancio?", "fuzz", False),
    ("cypher_inj",  "x'); MATCH (n) DETACH DELETE n; //", "fuzz", False),
    ("sql_inj",     "Robert'); DROP TABLE Entity;-- ", "fuzz", False),
    ("tmpl_inj",    "{{7*7}} ${jndi:ldap://x} <script>alert(1)</script>", "fuzz", False),
    ("path_trav",   "../../../../etc/passwd related to KAFKA", "fuzz", False),
    ("nullbyte",    "KAFKA-20688\x00\x00 related to", "fuzz", False),
    ("ctrl_chars",  "rel\tated\r\n to\x07 streams", "fuzz", False),
    ("very_long",   ("KAFKA related to streams " * 2000), "fuzz", False),
    ("unicode_zw",  "what​ is​ related​ to​ streams", "fuzz", False),
    ("quotes",      "\"'`related`'\" to 'streams'", "fuzz", False),
]


def stub_intent(router: TraceRouter) -> None:
    """Make intent classification hermetic: never hit the network/LLM."""
    w = config.ROUTER_WEIGHTS_CONCEPTUAL
    router._classify_intent_llm = lambda q: (w["vector"], w["graph"], "semantic")


def correctness_checks(router: TraceRouter, log: list[str]) -> int:
    """Single-threaded spot-checks. Returns number of FAILURES."""
    fails = 0
    resp = router.route("What is related to KAFKA-20688?")
    labels = {(r.label or "") for r in resp.results}
    log.append("hero result labels: " + repr(sorted(l for l in labels if l)[:15]))
    if "KAFKA-20688" not in labels:
        log.append("  FAIL: hero query did not surface KAFKA-20688 itself")
        fails += 1
    # at least one real human / component neighbor should ride along
    if len(resp.results) < 3:
        log.append("  FAIL: hero query returned < 3 results (%d)" % len(resp.results))
        fails += 1

    resp2 = router.route("What did Matthias J. Sax work on?")
    if not resp2.results:
        log.append("  FAIL: person query returned 0 results")
        fails += 1

    # accented name must round-trip with no replacement char
    resp3 = router.route("What did José Armando García Sancio work on?")
    joined = " ".join((r.label or "") for r in resp3.results)
    if "�" in joined:
        log.append("  FAIL: accented-name query produced U+FFFD in results")
        fails += 1
    log.append("correctness failures: %d" % fails)
    return fails


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Direct GraphRAG retrieval stress test.")
    p.add_argument("--db", type=Path, default=Path("graphs/apache__kafka.lbug"))
    p.add_argument("--iterations", type=int, default=400)
    p.add_argument("--concurrency", type=int, default=16)
    p.add_argument("--timeout", type=float, default=20.0, help="Per-call soft budget (s).")
    args = p.parse_args(argv)

    if not args.db.exists():
        print("ERROR: graph not found:", args.db)
        return 2

    print("Loading %s ..." % args.db)
    db = TraceDB(args.db)
    db.init_schema()
    router = TraceRouter(db)
    stub_intent(router)
    try:
        router.warm()
    except Exception as exc:  # noqa: BLE001
        print("warm() skipped:", exc)

    log: list[str] = []
    print("Running correctness checks ...")
    corr_fails = correctness_checks(router, log)

    n = args.iterations
    jobs = [BATTERY[i % len(BATTERY)] for i in range(n)]

    lat_by_cat: dict[str, list[float]] = defaultdict(list)
    empty_by_cat: dict[str, int] = defaultdict(int)
    errors: list[tuple[str, str, str]] = []   # (category, query[:60], traceback-last-line)
    slow: list[tuple[float, str]] = []
    statuses: Counter = Counter()

    def one(job: tuple[str, str, str, bool]) -> dict:
        _label, query, cat, _expect = job
        t0 = time.perf_counter()
        try:
            resp = router.route(query)
            dt = time.perf_counter() - t0
            return {"cat": cat, "dt": dt, "n": len(resp.results), "query": query, "err": None}
        except Exception:  # noqa: BLE001 — capture, don't abort the run
            dt = time.perf_counter() - t0
            tb = traceback.format_exc().strip().splitlines()[-1]
            return {"cat": cat, "dt": dt, "n": -1, "query": query, "err": tb}

    print("Hammering: %d calls, concurrency=%d ...\n" % (n, args.concurrency))
    wall0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futs = [pool.submit(one, j) for j in jobs]
        for f in as_completed(futs):
            r = f.result()
            if r["err"]:
                statuses["error"] += 1
                errors.append((r["cat"], r["query"][:60], r["err"]))
            else:
                statuses["ok"] += 1
                lat_by_cat[r["cat"]].append(r["dt"])
                if r["n"] == 0:
                    empty_by_cat[r["cat"]] += 1
                if r["dt"] > args.timeout:
                    slow.append((r["dt"], r["query"][:60]))
    wall = time.perf_counter() - wall0

    all_lat = sorted(v for vs in lat_by_cat.values() for v in vs)

    def pct(pp: float) -> float:
        return all_lat[min(len(all_lat) - 1, int(len(all_lat) * pp))] if all_lat else 0.0

    # ---- write full detail (UTF-8) ----
    detail = list(log)
    detail.append("")
    detail.append("=== latency by category (count, p50, p90, max) ===")
    for cat, vs in sorted(lat_by_cat.items()):
        s = sorted(vs)
        detail.append("  %-10s n=%-4d p50=%.3f p90=%.3f max=%.3f empty=%d" % (
            cat, len(s), s[len(s)//2], s[min(len(s)-1, int(len(s)*0.9))], s[-1],
            empty_by_cat.get(cat, 0)))
    detail.append("")
    detail.append("=== errors (%d) ===" % len(errors))
    for cat, q, tb in errors[:40]:
        detail.append("  [%s] %r -> %s" % (cat, q, tb))
    Path("scripts/_stress_graph.out.txt").write_text("\n".join(detail), encoding="utf-8")

    # ---- console summary (ASCII-safe) ----
    bar = "=" * 60
    print(bar)
    print("STRESS SUMMARY  db=%s" % args.db.name)
    print(bar)
    print("calls            %d (ok=%d, error=%d)" % (n, statuses["ok"], statuses["error"]))
    print("wall time        %.2fs   throughput %.0f calls/s" % (wall, n / wall if wall else 0))
    print("latency p50/p90  %.3f / %.3f s" % (pct(.5), pct(.9)))
    print("latency p99/max  %.3f / %.3f s" % (pct(.99), all_lat[-1] if all_lat else 0))
    print("correctness      %s (%d failures)" % ("PASS" if corr_fails == 0 else "FAIL", corr_fails))
    print("empty results    valid=%d offdomain=%d fuzz=%d" % (
        empty_by_cat.get("valid", 0), empty_by_cat.get("offdomain", 0),
        empty_by_cat.get("fuzz", 0)))
    print("slow (> %.0fs)     %d" % (args.timeout, len(slow)))
    print(bar)

    hard_fail = statuses["error"] > 0 or corr_fails > 0 or empty_by_cat.get("valid", 0) > 0
    if statuses["error"]:
        print("\n[!] %d calls threw exceptions (crash/injection/thread-safety):" % statuses["error"])
        for cat, q, tb in errors[:8]:
            print("    [%s] %r" % (cat, q))
            print("        %s" % tb)
    if empty_by_cat.get("valid", 0):
        print("\n[!] %d VALID demo queries returned ZERO results -- not demo-safe."
              % empty_by_cat["valid"])
    if not hard_fail:
        print("\n[ok] No crashes. Correctness passed. Every valid query returned hits.")
        print("     Fuzz/injection inputs degraded gracefully (no exceptions).")
    print("\nFull detail -> scripts/_stress_graph.out.txt")
    db.close()
    return 1 if hard_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
