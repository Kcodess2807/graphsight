"""Read a repo's merged PRs, issues and commits from the GitHub REST API."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
_PER_PAGE = 100          # GitHub's max page size
_MAX_PR_FILES = 3000     # GitHub's own hard cap on a PR's file list
_MAX_PR_REVIEWS = 200
_DETAIL_WORKERS = 8      # concurrent per-PR detail fetches


def _headers(token: str | None) -> dict[str, str]:
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _get(url: str, token: str | None, params: dict | None = None):
    import requests

    resp = requests.get(url, headers=_headers(token), params=params, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"GitHub API {resp.status_code} for {url}: {resp.text[:200]}")
    return resp.json()


def _paged(url: str, limit: int, token: str | None, params: dict,
           keep=lambda item: True) -> list[dict]:
    """Page an endpoint until `limit` kept items, or the listing runs out."""
    out: list[dict] = []
    page = 1
    while len(out) < limit:
        batch = _get(url, token, {**params, "per_page": _PER_PAGE, "page": page})
        if not batch:
            break
        out.extend(item for item in batch if keep(item))
        # a short page is the last page, which saves one request per call
        if len(batch) < _PER_PAGE:
            break
        page += 1
    return out[:limit]


def fetch_merged_prs(repo: str, limit: int, token: str | None) -> list[dict]:
    """Closed PRs, keeping only merged ones, until limit."""
    return _paged(f"{GITHUB_API}/repos/{repo}/pulls", limit, token,
                  {"state": "closed"}, keep=lambda pr: bool(pr.get("merged_at")))


def fetch_issues(repo: str, limit: int, token: str | None) -> list[dict]:
    """Issues only: the endpoint also returns PRs, which are dropped here."""
    if limit <= 0:
        return []
    return _paged(f"{GITHUB_API}/repos/{repo}/issues", limit, token,
                  {"state": "all"}, keep=lambda i: "pull_request" not in i)


def fetch_commits(repo: str, limit: int, token: str | None) -> list[dict]:
    if limit <= 0:
        return []
    return _paged(f"{GITHUB_API}/repos/{repo}/commits", limit, token, {})


def attach_pr_details(repo: str, prs: list[dict], token: str | None, *,
                      files: bool = False, reviews: bool = False,
                      workers: int = _DETAIL_WORKERS) -> None:
    """Fill each PR's `files` / `reviews` in place, one request per PR per kind."""
    if not (files or reviews):
        return

    def fetch_one(pr: dict) -> None:
        base = f"{GITHUB_API}/repos/{repo}/pulls/{pr['number']}"
        if files:
            pr["files"] = _paged(f"{base}/files", _MAX_PR_FILES, token, {})
        if reviews:
            pr["reviews"] = _paged(f"{base}/reviews", _MAX_PR_REVIEWS, token, {})

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for pr, fut in [(pr, pool.submit(fetch_one, pr)) for pr in prs if pr.get("number")]:
            try:
                fut.result()
            except Exception as exc:  # noqa: BLE001 — one bad PR isn't fatal
                logger.debug("[%s] detail fetch for #%s failed: %s", repo, pr["number"], exc)


def prune(prs: list[dict], issues: list[dict], commits: list[dict]) -> dict:
    """Only the fields the graph reads: a raw GitHub payload is mostly URLs."""
    user = lambda x: {"login": (x.get("user") or {}).get("login")}  # noqa: E731
    return {
        "pulls": [{
            **{k: pr.get(k) for k in ("number", "title", "body", "html_url",
                                      "merged_at", "closed_at", "created_at")},
            "user": user(pr),
            "files": [{"filename": f.get("filename")} for f in pr.get("files") or []],
            "reviews": [{"user": user(r)} for r in pr.get("reviews") or []],
        } for pr in prs],
        "issues": [{
            **{k: i.get(k) for k in ("number", "title", "body", "html_url", "created_at")},
            "user": user(i),
        } for i in issues],
        "commits": [{
            "sha": c.get("sha"),
            "author": {"login": (c.get("author") or {}).get("login")},
            "commit": {
                "message": (c.get("commit") or {}).get("message"),
                "author": {k: ((c.get("commit") or {}).get("author") or {}).get(k)
                           for k in ("name", "date")},
            },
        } for c in commits],
    }
