"""Pull closed GitHub PRs into the TraceRAG graph.

    python scripts/ingest_github.py --repo langchain-ai/langchain
    python scripts/ingest_github.py --repo owner/repo --limit 100 --reset

Set GITHUB_TOKEN in .env to raise the rate limit from 60/hr to 5000/hr.
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

_SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS.parent))
sys.path.insert(0, str(_SCRIPTS))

from tracerag import config                       # noqa: E402
from tracerag.db import TraceDB                    # noqa: E402
from tracerag.extract import EntityExtractor       # noqa: E402
from tracerag.curation import CurationEngine, IngestStats  # noqa: E402
from ingest import ingest_text                     # noqa: E402

logger = logging.getLogger("tracerag.github")

GITHUB_API = "https://api.github.com"
_PER_PAGE = 100  # GitHub's max page size


_MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_WS = re.compile(r"\s+")


def clean_pr_body(body: str | None) -> str:
    """Strip markdown images and HTML comments; collapse whitespace."""
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
    # rstrip trailing periods/spaces so we don't emit "...client.."
    body = clean_pr_body(pr.get("body")).rstrip(". ")
    text = f"PR #{number} merged by {author}. Title: {title}. Description: {body}."
    return f"pr-{number}", text


def fetch_merged_prs(repo: str, limit: int, token: str | None) -> list[dict]:
    """Page through closed PRs, keeping only merged ones (merged_at != null), until limit."""
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
            break
        merged.extend(pr for pr in batch if pr.get("merged_at"))
        page += 1
    return merged[:limit]


def repo_db_path(repo: str, graphs_dir: Path) -> Path:
    """Per-repo .lbug file, e.g. pallets/flask -> graphs/pallets__flask.lbug."""
    slug = re.sub(r"[^a-z0-9_]+", "-", repo.lower().replace("/", "__"))
    return graphs_dir / f"{slug}.lbug"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Ingest closed GitHub PRs into TraceRAG.")
    p.add_argument("--repo", nargs="+", required=True,
                   help='One or more repos, e.g. "pallets/flask psf/requests".')
    p.add_argument("--limit", type=int, default=50,
                   help="Max MERGED PRs to ingest per repo (protects rate limits).")
    p.add_argument("--db", type=Path, default=None,
                   help="Override output file (single-repo only; otherwise one "
                        "per-repo file is created under --graphs-dir).")
    p.add_argument("--graphs-dir", type=Path, default=None,
                   help="Directory for per-repo .lbug files (default backend/graphs).")
    p.add_argument("--reset", action="store_true",
                   help="Delete each target .lbug (+ sidecars) before ingesting.")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args(argv)


def ingest_repo(
    repo: str, db_path: Path, limit: int, reset: bool,
    token: str | None, extractor: EntityExtractor,
) -> None:
    """Fetch + ingest one repo's merged PRs into its own .lbug file."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if reset:
        for p in sorted(db_path.parent.glob(db_path.name + "*")):
            logger.info("[%s] reset: removing %s", repo, p.name)
            p.unlink()

    logger.info("[%s] fetching up to %d merged PRs", repo, limit)
    prs = fetch_merged_prs(repo, limit, token)
    logger.info("[%s] fetched %d merged PRs -> %s", repo, len(prs), db_path.name)

    db = TraceDB(db_path)
    db.init_schema()
    engine = CurationEngine(db)
    totals, skipped = IngestStats(), 0
    try:
        for pr in tqdm(prs, total=len(prs), desc=f"{repo}", unit="pr"):
            doc_id, text = assemble_text(pr)
            if not text.strip():
                skipped += 1
                continue
            totals.merge(
                ingest_text(engine, extractor, doc_id, text, source=pr.get("html_url"))
            )
        db.build_vector_index()
        logger.info(
            "[%s] done. %d PRs (%d skipped) | %d entities | "
            "created=%d fast=%d deep_yes=%d deep_no=%d llm=%d | "
            "rel=%d mentions=%d | nodes_in_db=%d",
            repo, totals.docs, skipped, totals.entities, totals.created,
            totals.fast_merged, totals.deep_merged_yes, totals.deep_merged_no,
            totals.ollama_calls, totals.relates_edges, totals.mentions_edges,
            db.count_nodes(),
        )
    finally:
        db.close()


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

    repo_root = config.PROJECT_ROOT.parent
    graphs_dir = args.graphs_dir or (config.PROJECT_ROOT / "graphs")
    if not graphs_dir.is_absolute():
        graphs_dir = repo_root / graphs_dir

    if args.db and len(args.repo) > 1:
        logger.warning("--db is ignored with multiple repos; using per-repo files.")

    extractor = EntityExtractor()
    for repo in args.repo:
        if args.db and len(args.repo) == 1:
            db_path = args.db if args.db.is_absolute() else (repo_root / args.db)
        else:
            db_path = repo_db_path(repo, graphs_dir)
        try:
            ingest_repo(repo, db_path, args.limit, args.reset, token, extractor)
        except Exception as exc:  # noqa: BLE001
            logger.error("[%s] FAILED: %s", repo, exc)

    logger.info("Batch complete. Graphs in %s", graphs_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
