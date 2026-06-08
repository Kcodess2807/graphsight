"""Batch-ingest a Jira CSV export into the TraceRAG graph.

    python scripts/ingest_kaggle_jira.py --file datasets/GFG_FINAL.csv --limit 100
    python scripts/ingest_kaggle_jira.py --file datasets/GFG_FINAL.csv --reset
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

import pandas as pd
from tqdm import tqdm

_SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS.parent))
sys.path.insert(0, str(_SCRIPTS))

from tracerag import config                       # noqa: E402
from tracerag.db import TraceDB                    # noqa: E402
from tracerag.extract import EntityExtractor       # noqa: E402
from tracerag.curation import CurationEngine, IngestStats  # noqa: E402
from ingest import ingest_text                     # noqa: E402

logger = logging.getLogger("tracerag.kaggle")

# pandas suffixes repeated columns with .1/.2/... in wide exports
_COMPONENT_COLS = ["Component/s", "Component/s.1", "Component/s.2", "Component/s.3"]
_LABEL_COLS = ["Labels"] + [f"Labels.{i}" for i in range(1, 7)]


_CODE_BLOCK = re.compile(r"\{code(:[^}]*)?\}.*?\{code\}", re.DOTALL | re.IGNORECASE)
_NOFORMAT = re.compile(r"\{noformat\}.*?\{noformat\}", re.DOTALL | re.IGNORECASE)
_HTML_TAG = re.compile(r"<[^>]+>")
_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")    # [text](url) -> text
_JIRA_LINK = re.compile(r"\[([^|\]]+)\|[^\]]+\]")  # [text|url]  -> text
_BRACE_MACRO = re.compile(r"\{[^}]*\}")            # leftover {quote}/{panel}/{color}
_URL = re.compile(r"https?://\S+")
_WS = re.compile(r"\s+")


def clean_jira_text(raw: str) -> str:
    """Strip HTML, markdown/Jira links, {code}/{noformat}/{macro} blocks and URLs."""
    if not raw:
        return ""
    t = _CODE_BLOCK.sub(" ", raw)
    t = _NOFORMAT.sub(" ", t)
    t = _HTML_TAG.sub(" ", t)
    t = _MD_LINK.sub(r"\1", t)
    t = _JIRA_LINK.sub(r"\1", t)
    t = _BRACE_MACRO.sub(" ", t)
    t = _URL.sub(" ", t)
    return _WS.sub(" ", t).strip()


def _combine(row: pd.Series, cols: list[str]) -> str:
    """Join distinct, non-empty values from a set of (possibly repeated) columns."""
    seen, out = set(), []
    for c in cols:
        v = str(row.get(c, "")).strip()
        if v and v.lower() != "nan" and v not in seen:
            seen.add(v)
            out.append(v)
    return ", ".join(out)


def assemble_text(row: pd.Series) -> tuple[str, str]:
    """Build (doc_id, clean text blob) the existing pipeline can parse."""
    def f(col: str) -> str:
        v = str(row.get(col, "")).strip()
        return "" if v.lower() == "nan" else v

    key = f("Issue key")
    parts: list[str] = []
    summary = f("Summary")
    if key or summary:
        parts.append(f"Ticket {key}: {summary}.".strip())
    for label, col in (("Type", "Issue Type"), ("Status", "Status"),
                       ("Priority", "Priority"), ("Project", "Project name")):
        if f(col):
            parts.append(f"{label}: {f(col)}.")
    if f("Assignee"):
        parts.append(f"Assigned to {f('Assignee')}.")
    if f("Reporter"):
        parts.append(f"Reported by {f('Reporter')}.")
    components = _combine(row, _COMPONENT_COLS)
    if components:
        parts.append(f"Component: {components}.")
    labels = _combine(row, _LABEL_COLS)
    if labels:
        parts.append(f"Labels: {labels}.")
    desc = clean_jira_text(f("Description"))
    if desc:
        parts.append(f"Description: {desc}")
    return key, " ".join(parts)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Ingest a Jira CSV export into TraceRAG.")
    p.add_argument("--file", type=Path, required=True, help="Path to the Jira CSV.")
    p.add_argument("--limit", type=int, default=None,
                   help="Ingest only the first N rows (for quick tests).")
    p.add_argument("--db", type=Path, default=config.DB_PATH)
    p.add_argument("--reset", action="store_true",
                   help="Delete the existing .lbug (+ sidecars) before ingesting.")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(name)s  %(message)s",
    )
    for noisy in ("httpx", "httpcore", "openai", "sentence_transformers"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    if args.reset:
        for p in sorted(args.db.parent.glob(args.db.name + "*")):
            logger.info("Reset: removing %s", p)
            p.unlink()

    logger.info("Reading %s", args.file)
    df = pd.read_csv(args.file, low_memory=False).fillna("")
    if args.limit:
        df = df.head(args.limit)
    logger.info("Loaded %d rows, %d columns", len(df), df.shape[1])

    extractor = EntityExtractor()
    db = TraceDB(args.db)
    db.init_schema()
    engine = CurationEngine(db)

    totals = IngestStats()
    skipped = 0
    try:
        for i, row in tqdm(df.iterrows(), total=len(df), desc="ingesting jira", unit="ticket"):
            doc_id, text = assemble_text(row)
            if not text.strip():
                skipped += 1
                continue
            totals.merge(ingest_text(engine, extractor, doc_id or f"row-{i}", text))

        db.build_vector_index()
        logger.info(
            "Done. %d rows ingested (%d skipped) | %d entities | "
            "created=%d fast=%d deep_yes=%d deep_no=%d llm=%d | "
            "rel=%d mentions=%d | nodes_in_db=%d",
            totals.docs, skipped, totals.entities, totals.created, totals.fast_merged,
            totals.deep_merged_yes, totals.deep_merged_no, totals.ollama_calls,
            totals.relates_edges, totals.mentions_edges, db.count_nodes(),
        )
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
