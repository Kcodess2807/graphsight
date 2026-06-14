"""Ingest real Jira tickets straight from a public Jira REST API.

Pulls issues for one project (default: Apache Kafka on issues.apache.org),
maps each to the same text shape the CSV pipeline uses, and runs them through
the existing extraction -> curation -> graph pipeline.

    # see what would be ingested, no DB / no GLiNER:
    python scripts/ingest_jira_api.py --project KAFKA --limit 20 --dry-run

    # build a fresh graph the dropdown will auto-discover:
    python scripts/ingest_jira_api.py --project KAFKA --limit 150 \
        --db graphs/apache__kafka.lbug --reset

Any public Jira works via --base, e.g. Apache SPARK / LUCENE / FLINK, or
Hyperledger, etc. Requires no auth for public instances.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import urllib.parse
import urllib.request
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS.parent))
sys.path.insert(0, str(_SCRIPTS))

from tracerag import config                       # noqa: E402
from tracerag.db import TraceDB                    # noqa: E402
from tracerag.extract import EntityExtractor       # noqa: E402
from tracerag.curation import CurationEngine, IngestStats  # noqa: E402
from ingest import ingest_text                     # noqa: E402
from ingest_kaggle_jira import clean_jira_text     # noqa: E402  (reuse markup stripper)

logger = logging.getLogger("tracerag.jira_api")

DEFAULT_BASE = "https://issues.apache.org/jira"
_FIELDS = "key,summary,issuetype,status,priority,assignee,reporter,components,labels,description"
_PAGE = 100  # Jira caps maxResults at 100 for most instances


def _name(obj: dict | None, key: str = "name") -> str:
    """Safely pull a display string out of a nested Jira field object."""
    if not isinstance(obj, dict):
        return ""
    return str(obj.get(key) or "").strip()


def assemble_text(issue: dict) -> tuple[str, str]:
    """Build (doc_id, clean text blob) from one Jira REST issue record."""
    f = issue.get("fields") or {}
    key = str(issue.get("key") or "").strip()

    parts: list[str] = []
    summary = str(f.get("summary") or "").strip()
    if key or summary:
        parts.append(f"Ticket {key}: {summary}.".strip())

    for label, val in (
        ("Type", _name(f.get("issuetype"))),
        ("Status", _name(f.get("status"))),
        ("Priority", _name(f.get("priority"))),
    ):
        if val:
            parts.append(f"{label}: {val}.")

    assignee = _name(f.get("assignee"), "displayName")
    if assignee:
        parts.append(f"Assigned to {assignee}.")
    reporter = _name(f.get("reporter"), "displayName")
    if reporter:
        parts.append(f"Reported by {reporter}.")

    components = ", ".join(
        c.get("name", "") for c in (f.get("components") or []) if c.get("name")
    )
    if components:
        parts.append(f"Component: {components}.")
    labels = ", ".join(l for l in (f.get("labels") or []) if l)
    if labels:
        parts.append(f"Labels: {labels}.")

    desc = clean_jira_text(str(f.get("description") or ""))
    if desc:
        parts.append(f"Description: {desc}")

    return key, " ".join(parts)


def fetch_issues(base: str, jql: str, limit: int) -> list[dict]:
    """Page through the Jira search API until `limit` issues are collected."""
    out: list[dict] = []
    start = 0
    while len(out) < limit:
        page_size = min(_PAGE, limit - len(out))
        params = urllib.parse.urlencode(
            {"jql": jql, "startAt": start, "maxResults": page_size, "fields": _FIELDS}
        )
        url = f"{base.rstrip('/')}/rest/api/2/search?{params}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        logger.info("GET %s (have %d/%d)", url.split("?")[0], len(out), limit)
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (trusted host)
            data = json.loads(resp.read().decode("utf-8"))
        issues = data.get("issues") or []
        if not issues:
            break
        out.extend(issues)
        total = data.get("total", 0)
        start += len(issues)
        if start >= total:
            break
    return out[:limit]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Ingest Jira tickets from a public REST API.")
    p.add_argument("--project", default="KAFKA", help="Jira project key, e.g. KAFKA, SPARK.")
    p.add_argument("--base", default=DEFAULT_BASE, help="Jira base URL.")
    p.add_argument("--jql", default=None,
                   help="Override the JQL (default: project=<PROJECT> ORDER BY created DESC).")
    p.add_argument("--limit", type=int, default=150, help="Number of issues to ingest.")
    p.add_argument("--db", type=Path, default=config.DB_PATH)
    p.add_argument("--reset", action="store_true",
                   help="Delete the existing .lbug (+ sidecars) before ingesting.")
    p.add_argument("--dry-run", action="store_true",
                   help="Fetch + assemble + print samples; no GLiNER, no DB writes.")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(name)s  %(message)s",
    )
    for noisy in ("httpx", "httpcore", "openai", "sentence_transformers", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    jql = args.jql or f"project={args.project} ORDER BY created DESC"
    logger.info("Fetching up to %d issues | %s | %s", args.limit, args.base, jql)
    issues = fetch_issues(args.base, jql, args.limit)
    logger.info("Fetched %d issues", len(issues))

    if args.dry_run:
        shown = 0
        empty = 0
        for issue in issues:
            doc_id, text = assemble_text(issue)
            if not text.strip():
                empty += 1
                continue
            if shown < 5:
                logger.info("--- %s ---\n%s", doc_id, text[:400])
                shown += 1
        logger.info("DRY RUN: %d ingestable, %d empty, of %d fetched",
                    len(issues) - empty, empty, len(issues))
        return 0

    if args.reset:
        for p in sorted(args.db.parent.glob(args.db.name + "*")):
            logger.info("Reset: removing %s", p)
            p.unlink()

    extractor = EntityExtractor()
    db = TraceDB(args.db)
    db.init_schema()
    engine = CurationEngine(db)

    totals = IngestStats()
    skipped = 0
    try:
        for i, issue in enumerate(issues):
            doc_id, text = assemble_text(issue)
            if not text.strip():
                skipped += 1
                continue
            totals.merge(ingest_text(engine, extractor, doc_id or f"issue-{i}", text))
            if (i + 1) % 25 == 0:
                logger.info("  ingested %d/%d", i + 1, len(issues))

        db.build_vector_index()
        logger.info(
            "Done. %d issues ingested (%d skipped) | %d entities | "
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
