"""Live ingestion connector: pull closed GitHub PRs into the TraceRAG graph.

Queries the GitHub REST API, cleans each PR's markdown, assembles a compact
text blob, and runs it through the shared ``ingest_text`` pipeline (spaCy/GLiNER
extraction -> two-tier curation -> .lbug write). The HNSW index is rebuilt once
at the end.

    python scripts/ingest_github.py --repo langchain-ai/langchain
    python scripts/ingest_github.py --repo owner/repo --limit 100 --reset

Auth: set GITHUB_TOKEN in .env. Unauthenticated requests are capped at 60/hr by
GitHub; an authenticated token raises that to 5000/hr.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from pathlib import Path

import requests
from tqdm import tqdm

# Make both `tracerag` (../) and the sibling `ingest` module importable.
_SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS.parent))
sys.path.insert(0, str(_SCRIPTS))

from tracerag import config                       # noqa: E402  (also loads .env)
from tracerag.db import TraceDB                    # noqa: E402
from tracerag.extract import EntityExtractor       # noqa: E402
from tracerag.curation import CurationEngine, IngestStats  # noqa: E402
from ingest import ingest_text                     # noqa: E402  (reuse the pipeline)

logger = logging.getLogger("tracerag.github")

GITHUB_API = "https://api.github.com"
_PER_PAGE = 100  # GitHub's max page size


# --------------------------------------------------------------------------- #
# Cleaning — GitHub PR bodies are full of markup that confuses spaCy
# --------------------------------------------------------------------------- #
_MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")   # ![alt](url)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)  # <!-- hidden -->
_WS = re.compile(r"\s+")


def clean_pr_body(body: str | None) -> str:
    """Strip markdown images and HTML comments; collapse whitespace.

    Handles ``None`` bodies (GitHub returns null for empty descriptions).
    """
    if not body:
        return ""
    t = _MD_IMAGE.sub(" ", body)
    t = _HTML_COMMENT.sub(" ", t)
    return _WS.sub(" ", t).strip()


def assemble_text(pr: dict) -> tuple[str, str]:
    """Build (doc_id, clean text blob) the existing pipeline can parse."""
    number = pr.get("number")
    title = (pr.get("title") or "").strip()
    author = (pr.get("user") or {}).get("login") or "unknown"
    # rstrip trailing periods/spaces so we don't emit "...client.." — keeps the
    # ingested text pristine even when the PR body already ends in a period.
    body = clean_pr_body(pr.get("body")).rstrip(". ")
    text = f"PR #{number} merged by {author}. Title: {title}. Description: {body}."
    return f"pr-{number}", text


# --------------------------------------------------------------------------- #
# GitHub API
# --------------------------------------------------------------------------- #
def fetch_merged_prs(repo: str, limit: int, token: str | None) -> list[dict]:
    """Page through closed PRs, keeping only MERGED ones, until ``limit`` is hit.

    GitHub has no "merged" filter — ``state=closed`` returns both merged and
    rejected/abandoned PRs. We must drop the rejected ones (``merged_at`` is
    null): ingesting them as "merged" would poison the graph with edges to code
    that never reached main, so an incident trace could blame the wrong author.
    Filtering BEFORE the limit ensures we return ``limit`` *merged* PRs, not
    ``limit`` closed PRs of which only some merged.
    """
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    merged: list[dict] = []
    page = 1
    while len(merged) < limit:
        resp = requests.get(
            f"{GITHUB_API}/repos/{repo}/pulls",
            headers=headers,
            params={"state": "closed", "per_page": _PER_PAGE, "page": page},
            timeout=30,
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"GitHub API {resp.status_code} for {repo}: {resp.text[:200]}"
            )
        batch = resp.json()
        if not batch:
            break  # no more pages
        merged.extend(pr for pr in batch if pr.get("merged_at"))
        page += 1
    return merged[:limit]


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Ingest closed GitHub PRs into TraceRAG.")
    p.add_argument("--repo", required=True,
                   help='Target repository, e.g. "owner/repo-name".')
    p.add_argument("--limit", type=int, default=50,
                   help="Max PRs to ingest (protects API rate limits).")
    p.add_argument("--db", type=Path, default=Path("backend/_live_test.lbug"),
                   help="Target .lbug file (default keeps production safe).")
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
    for noisy in ("httpx", "httpcore", "openai", "urllib3", "sentence_transformers"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    token = os.getenv("GITHUB_TOKEN")
    if not token:
        logger.warning("GITHUB_TOKEN not set — unauthenticated requests are capped "
                       "at 60/hr. Add it to .env to raise the limit.")

    # Anchor relative --db paths at the repo root (config.PROJECT_ROOT is the
    # `backend/` dir, so its parent is the repo root). This makes the documented
    # default "backend/_live_test.lbug" resolve correctly whether you run from
    # the repo root or from inside backend/ — no more backend/backend/... .
    repo_root = config.PROJECT_ROOT.parent
    db_path = args.db if args.db.is_absolute() else (repo_root / args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if args.reset:
        for p in sorted(db_path.parent.glob(db_path.name + "*")):
            logger.info("Reset: removing %s", p)
            p.unlink()

    logger.info("Fetching up to %d MERGED PRs from %s", args.limit, args.repo)
    prs = fetch_merged_prs(args.repo, args.limit, token)
    logger.info("Fetched %d merged PRs", len(prs))

    extractor = EntityExtractor()
    db = TraceDB(db_path)
    db.init_schema()
    engine = CurationEngine(db)

    totals = IngestStats()
    skipped = 0
    try:
        for pr in tqdm(prs, total=len(prs), desc="ingesting PRs", unit="pr"):
            doc_id, text = assemble_text(pr)
            if not text.strip():
                skipped += 1
                continue
            totals.merge(ingest_text(engine, extractor, doc_id, text))

        db.build_vector_index()
        logger.info(
            "Done. %d PRs ingested (%d skipped) | %d entities | "
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
