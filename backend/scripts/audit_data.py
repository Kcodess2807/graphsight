"""Data-integrity linter for the TraceRAG graph.

    python scripts/audit_data.py [--db memory.lbug] [--alias-threshold 0.85] [--json report.json]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tracerag import config                      # noqa: E402
from tracerag.db import TraceDB                   # noqa: E402

logger = logging.getLogger("tracerag.audit")

_OWNABLE_TYPES = ("Service", "Repo", "Ticket", "PR", "Tool")
_OWNER_TYPES = ("Person", "Team")


def find_orphaned_nodes(db: TraceDB) -> list[dict]:
    """Entities with no RELATES_TO edges (isolated in the entity graph)."""
    rows = db._records(db.execute(
        f"MATCH (e:{config.NODE_TABLE}) "
        f"OPTIONAL MATCH (e)-[r:{config.REL_TABLE}]-(:{config.NODE_TABLE}) "
        f"RETURN e.id AS id, e.label AS label, e.type AS type, count(r) AS degree;"
    ))
    return [r for r in rows if int(r["degree"]) == 0]


def find_conflicting_edges(db: TraceDB) -> list[dict]:
    """Ownable nodes linked to more than one distinct Person/Team."""
    rows = db._records(db.execute(
        f"MATCH (a:{config.NODE_TABLE})-[:{config.REL_TABLE}]-(b:{config.NODE_TABLE}) "
        f"WHERE a.type IN $ownable AND b.type IN $owners "
        f"RETURN a.id AS aid, a.label AS alabel, a.type AS atype, "
        f"b.label AS owner, b.type AS owner_type;",
        {"ownable": list(_OWNABLE_TYPES), "owners": list(_OWNER_TYPES)},
    ))
    grouped: dict[str, dict] = {}
    for r in rows:
        g = grouped.setdefault(r["aid"], {
            "id": r["aid"], "label": r["alabel"], "type": r["atype"], "owners": set()
        })
        g["owners"].add(f'{r["owner"]} ({r["owner_type"]})')
    conflicts = []
    for g in grouped.values():
        if len(g["owners"]) > 1:
            g["owners"] = sorted(g["owners"])
            conflicts.append(g)
    return conflicts


def find_alias_drift(db: TraceDB, threshold: float) -> list[dict]:
    """Separate nodes with near-duplicate embeddings (cosine >= threshold)."""
    rows = db._records(db.execute(
        f"MATCH (e:{config.NODE_TABLE}) "
        f"RETURN e.id AS id, e.label AS label, e.type AS type, e.embedding AS emb;"
    ))
    rows = [r for r in rows if r.get("emb") is not None]
    if len(rows) < 2:
        return []
    mat = np.asarray([r["emb"] for r in rows], dtype=np.float32)  # pre-normalized
    sims = mat @ mat.T
    pairs = []
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            s = float(sims[i, j])
            if s >= threshold:
                pairs.append({
                    "a": rows[i]["label"], "a_type": rows[i]["type"],
                    "b": rows[j]["label"], "b_type": rows[j]["type"],
                    "similarity": round(s, 4),
                })
    pairs.sort(key=lambda p: p["similarity"], reverse=True)
    return pairs


def _section(title: str, items: list, render) -> None:
    print(f"\n{'=' * 70}\n {title}  ({len(items)} found)\n{'-' * 70}")
    if not items:
        print("  (none)")
        return
    for it in items[:40]:
        print("  " + render(it))
    if len(items) > 40:
        print(f"  ... and {len(items) - 40} more")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="TraceRAG data-integrity linter.")
    p.add_argument("--db", type=Path, default=config.DB_PATH)
    p.add_argument("--alias-threshold", type=float, default=config.DEEP_MERGE_THRESHOLD,
                   help="Cosine >= this between distinct nodes flags alias drift.")
    p.add_argument("--json", type=Path, default=None, help="Also write the report as JSON.")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)

    db = TraceDB(args.db)
    try:
        total_nodes = db.count_nodes()
        orphaned = find_orphaned_nodes(db)
        conflicts = find_conflicting_edges(db)
        drift = find_alias_drift(db, args.alias_threshold)
    finally:
        db.close()

    print(f"\nTraceRAG data audit — {args.db}  ({total_nodes} entities)")
    _section("ORPHANED NODES (0 RELATES_TO edges)", orphaned,
             lambda r: f'{r["label"]!r} ({r["type"]})  id={r["id"]}')
    _section("CONFLICTING OWNERSHIP (>1 Person/Team)", conflicts,
             lambda c: f'{c["label"]!r} ({c["type"]}) -> {", ".join(c["owners"])}')
    _section(f"ALIAS DRIFT (cosine >= {args.alias_threshold})", drift,
             lambda d: f'{d["similarity"]}  {d["a"]!r} ({d["a_type"]})  ~  {d["b"]!r} ({d["b_type"]})')

    summary = {
        "db": str(args.db), "total_nodes": total_nodes,
        "orphaned": orphaned, "conflicts": conflicts, "alias_drift": drift,
    }
    print(f"\n{'=' * 70}\n SUMMARY: {len(orphaned)} orphaned | "
          f"{len(conflicts)} ownership conflicts | {len(drift)} alias-drift pairs\n")
    if args.json:
        args.json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"Wrote JSON report -> {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
