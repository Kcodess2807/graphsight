"""Pull closed GitHub PRs into the TraceRAG graph.

    python scripts/ingest_github.py --repo langchain-ai/langchain
    python scripts/ingest_github.py --repo owner/repo --limit 100 --reset
    python scripts/ingest_github.py --repo owner/repo --issues 50 --commits 50 --files

Two passes write into the same graph:

  * text     — PR prose through extraction + curation (fuzzy CO_OCCURS edges)
  * structure — the same payloads through GitHubGraphBuilder, which reads
    authorship, reviews, "Fixes #N" and touched files as typed, timestamped
    edges. These are facts from the API, not guesses from word proximity.

Set GITHUB_TOKEN in .env to raise the rate limit from 60/hr to 5000/hr.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path

from tqdm import tqdm

_SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS.parent))
sys.path.insert(0, str(_SCRIPTS))

from graphsight_memory.db import TraceDB                    # noqa: E402
from graphsight_memory.extract import EntityExtractor       # noqa: E402
from graphsight_memory.curation import CurationEngine, IngestStats  # noqa: E402
from graphsight_memory.github import (  # noqa: E402
    attach_pr_details, fetch_commits, fetch_issues, fetch_merged_prs, prune)
from graphsight_memory.github_graph import GitHubGraphBuilder       # noqa: E402
from ingest import ingest_text                     # noqa: E402

logger = logging.getLogger("tracerag.github")

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
    p.add_argument("--issues", type=int, default=0,
                   help="Also ingest up to N issues (REPORTED edges, RESOLVES targets).")
    p.add_argument("--commits", type=int, default=0,
                   help="Also ingest up to N commits (AUTHORED + 'Fixes #N' edges).")
    p.add_argument("--files", action="store_true",
                   help="Fetch each PR's changed files for TOUCHES edges. "
                        "Costs one extra API request per PR.")
    p.add_argument("--reviews", action="store_true",
                   help="Fetch each PR's reviews for REVIEWED edges. Costs one "
                        "extra API request per PR. Without this there are no "
                        "REVIEWED edges — the PR listing only reports pending "
                        "review requests, not who actually reviewed.")
    p.add_argument("--no-text", action="store_true",
                   help="Skip the prose/curation pass; write structured edges only.")
    p.add_argument("--db", type=Path, default=None,
                   help="Override output file (single-repo only; otherwise one "
                        "per-repo file is created under --graphs-dir).")
    p.add_argument("--graphs-dir", type=Path, default=None,
                   help="Directory for per-repo .lbug files (default backend/graphs).")
    p.add_argument("--snapshot", type=Path, default=None,
                   help="Read the repo from this JSON file instead of GitHub; if it "
                        "doesn't exist, fetch and write it. Gives repeatable builds.")
    p.add_argument("--reset", action="store_true",
                   help="Delete each target .lbug (+ sidecars) before ingesting.")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args(argv)


def ingest_repo(
    repo: str, db_path: Path, args: argparse.Namespace,
    token: str | None, extractor: EntityExtractor | None,
) -> None:
    """Fetch + ingest one repo into its own .lbug file (text pass, then structure)."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if args.reset:
        for p in sorted(db_path.parent.glob(db_path.name + "*")):
            logger.info("[%s] reset: removing %s", repo, p.name)
            p.unlink()

    if args.snapshot and args.snapshot.exists():
        frozen = json.loads(args.snapshot.read_text(encoding="utf-8"))
        prs, issues, commits = frozen["pulls"], frozen["issues"], frozen["commits"]
    else:
        logger.info("[%s] fetching up to %d merged PRs", repo, args.limit)
        prs = fetch_merged_prs(repo, args.limit, token)
        issues = fetch_issues(repo, args.issues, token)
        commits = fetch_commits(repo, args.commits, token)
        attach_pr_details(repo, prs, token, files=args.files, reviews=args.reviews)
        if args.snapshot:
            frozen = prune(prs, issues, commits)
            args.snapshot.write_text(json.dumps(frozen, indent=1), encoding="utf-8")
    logger.info(
        "[%s] fetched %d PRs, %d issues, %d commits -> %s",
        repo, len(prs), len(issues), len(commits), db_path.name,
    )

    db = TraceDB(db_path)
    db.init_schema()
    engine = CurationEngine(db)
    totals, skipped = IngestStats(), 0
    try:
        if not args.no_text:
            for pr in tqdm(prs, total=len(prs), desc=f"{repo}", unit="pr"):
                doc_id, text = assemble_text(pr)
                if not text.strip():
                    skipped += 1
                    continue
                totals.merge(
                    ingest_text(engine, extractor, doc_id, text,
                                source=pr.get("html_url"))
                )

        # structured pass: relations read from the payload, not inferred. Its node
        # ids differ from the text pass, so these edges sit beside CO_OCCURS guesses.
        builder = GitHubGraphBuilder(db, engine.embed, repo)
        graph = builder.build(pulls=prs, issues=issues, commits=commits)

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
        logger.info(
            "[%s] structure: %d nodes, %d typed edges %s",
            repo, graph.nodes, graph.edges,
            dict(sorted(graph.by_relation.items(), key=lambda kv: -kv[1])),
        )
        for flag, enabled, relation in (("--files", args.files, "TOUCHES"),
                                        ("--reviews", args.reviews, "REVIEWED")):
            if not enabled:
                logger.info("[%s] no %s edges — rerun with %s (one extra "
                            "request per PR).", repo, relation, flag)
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

    backend_dir = Path(__file__).resolve().parents[1]
    repo_root = backend_dir.parent
    graphs_dir = args.graphs_dir or (backend_dir / "graphs")
    if not graphs_dir.is_absolute():
        graphs_dir = repo_root / graphs_dir

    if args.db and len(args.repo) > 1:
        logger.warning("--db is ignored with multiple repos; using per-repo files.")

    # --no-text skips extraction entirely; don't pay to load the models
    extractor = None if args.no_text else EntityExtractor()
    for repo in args.repo:
        if args.db and len(args.repo) == 1:
            db_path = args.db if args.db.is_absolute() else (repo_root / args.db)
        else:
            db_path = repo_db_path(repo, graphs_dir)
        try:
            ingest_repo(repo, db_path, args, token, extractor)
        except Exception as exc:  # noqa: BLE001
            logger.error("[%s] FAILED: %s", repo, exc)

    logger.info("Batch complete. Graphs in %s", graphs_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
