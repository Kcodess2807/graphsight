"""GitHub delta fetcher — pulls only what changed since a repo's last cursor.

Uses the GitHub REST *issues* endpoint (which returns BOTH issues and PRs, and
carries a ``pull_request`` sub-object with ``merged_at``) filtered by ``since`` —
the standard way to page "everything updated after a timestamp" in one call. The
cursor is an ISO8601 timestamp; we return the max ``updated_at`` of the batch as
the new cursor.

Modular by design:
  * pass a ``github_token`` (or set GITHUB_TOKEN) to hit the real API — required to
    escape the brutal 60 req/hr unauthenticated limit, and enough to point this at
    ``tiangolo/fastapi`` right now.
  * with no token (and no injected transport) it falls back to the fixed MOCK
    batch, so offline tests and local dev keep working. Force mock explicitly with
    TRACERAG_GITHUB_MOCK=1.

Rate limits raise ``GitHubRateLimitError`` (with the reset time) rather than
crashing, so the Celery task can self.retry instead of burning the job.
"""

import logging
import os
import time
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger("tracerag.github")

GITHUB_API = os.getenv("GITHUB_API_URL", "https://api.github.com")


# --- exceptions the worker can reason about --------------------------------
class GitHubError(Exception):
    """Any non-recoverable GitHub API failure (bad repo, unexpected status)."""


class GitHubAuthError(GitHubError):
    """Token missing/invalid (401)."""


class GitHubRateLimitError(GitHubError):
    """Primary or secondary rate limit hit (403 remaining=0 / 429). Carries the
    delay so the caller can retry after it clears."""

    def __init__(self, retry_after: int | None = None, reset_at: int | None = None):
        self.retry_after = retry_after
        self.reset_at = reset_at
        super().__init__(
            f"GitHub rate limit exceeded (retry_after={retry_after}s, reset_at={reset_at})"
        )


# --- normalized delta contract (unchanged shape used by the pipeline) ------
@dataclass
class DeltaItem:
    external_id: str
    kind: str                 # 'PR' | 'Issue'
    number: int
    title: str
    body: str
    author: str
    url: str
    updated_at: str           # ISO8601; also advances the cursor
    merged: bool = False       # PRs only: was it merged?


@dataclass
class DeltaResult:
    items: list[DeltaItem] = field(default_factory=list)
    new_cursor: str = ""


# Fixed fake payload for the mock path (no token / offline). Entity-rich text.
_MOCK_FIRST_SYNC = [
    DeltaItem("PR-101", "PR", 101,
              "Fix null pointer in PaymentService refund path",
              "PR #101 by alice-dev fixes INFRA-42: PaymentService threw a null "
              "pointer when the auth module returned an expired token during a "
              "refund. Adds a guard and a regression test.",
              "alice-dev", "https://github.com/acme/payments/pull/101",
              "2026-07-15T10:00:00Z", merged=True),
    DeltaItem("PR-102", "PR", 102,
              "Add retry/backoff to the BillingService consumer",
              "PR #102 by bob-ops wires exponential backoff into the BillingService "
              "Kafka consumer after INFRA-58 showed dropped events under load. "
              "Reviewed by alice-dev.",
              "bob-ops", "https://github.com/acme/payments/pull/102",
              "2026-07-16T09:30:00Z", merged=True),
    DeltaItem("ISSUE-58", "Issue", 58,
              "BillingService drops events under load (INFRA-58)",
              "Issue INFRA-58: under sustained load the BillingService consumer "
              "silently drops Kafka events. Suspected backpressure in the "
              "PaymentService callback. Reported by carol-sre.",
              "carol-sre", "https://github.com/acme/payments/issues/58",
              "2026-07-14T18:20:00Z", merged=False),
]


class GitHubDeltaClient:
    """Fetches PRs/issues for one repo since a cursor, with pagination + rate-limit
    handling. Bounded by ``max_items`` so a first sync of a huge repo (e.g. fastapi)
    grabs recent history rather than the entire backlog."""

    def __init__(
        self, repo_full_name: str, cursor: str | None = None,
        token: str | None = None, *, transport=None, max_items: int | None = None,
    ) -> None:
        self.repo_full_name = repo_full_name
        self.cursor = cursor
        self.token = token or os.getenv("GITHUB_TOKEN")
        self._transport = transport  # httpx.MockTransport in tests
        self.max_items = int(max_items or os.getenv("TRACERAG_GITHUB_MAX_ITEMS", "100"))

    def _use_mock(self) -> bool:
        if os.getenv("TRACERAG_GITHUB_MOCK", "").lower() in ("1", "true", "yes"):
            return True
        # no credentials and no injected transport -> can't/shouldn't hit real API
        return self.token is None and self._transport is None

    def fetch_recent_prs_and_commits(self) -> DeltaResult:
        if self._use_mock():
            logger.info("GitHub client in MOCK mode for %s", self.repo_full_name)
            return self._mock_result()
        return self._fetch_real()

    # --- mock path ----------------------------------------------------------
    def _mock_result(self) -> DeltaResult:
        if self.cursor:
            return DeltaResult(items=[], new_cursor=self.cursor)
        items = list(_MOCK_FIRST_SYNC)
        return DeltaResult(items=items, new_cursor=max(i.updated_at for i in items))

    # --- real path ----------------------------------------------------------
    def _headers(self) -> dict:
        h = {"Accept": "application/vnd.github+json",
             "X-GitHub-Api-Version": "2022-11-28"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def _client(self) -> httpx.Client:
        kwargs = dict(base_url=GITHUB_API, headers=self._headers(), timeout=30.0)
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.Client(**kwargs)

    def _fetch_real(self) -> DeltaResult:
        # incremental: oldest-first after the cursor so a capped batch advances the
        # cursor safely (no gap); first sync: newest-first to grab recent history.
        params = {
            "state": "all", "sort": "updated", "per_page": 100,
            "direction": "asc" if self.cursor else "desc",
        }
        if self.cursor:
            params["since"] = self.cursor

        items: list[DeltaItem] = []
        url = f"/repos/{self.repo_full_name}/issues"
        with self._client() as client:
            while url and len(items) < self.max_items:
                resp = client.get(url, params=params)
                self._raise_for_status(resp)
                batch = resp.json()
                if not batch:
                    break
                for raw in batch:
                    item = self._normalize(raw)
                    if item is not None:
                        items.append(item)
                        if len(items) >= self.max_items:
                            break
                # follow RFC5988 Link: rel="next" (absolute URL already has params)
                nxt = resp.links.get("next", {}).get("url")
                url, params = (nxt, None) if nxt else (None, None)

        if not items:
            return DeltaResult(items=[], new_cursor=self.cursor or "")
        new_cursor = max(i.updated_at for i in items)
        logger.info("GitHub %s: fetched %d items (cursor -> %s)",
                    self.repo_full_name, len(items), new_cursor)
        return DeltaResult(items=items, new_cursor=new_cursor)

    @staticmethod
    def _normalize(raw: dict) -> DeltaItem | None:
        number = raw.get("number")
        if number is None:
            return None
        pr = raw.get("pull_request")
        is_pr = pr is not None
        kind = "PR" if is_pr else "Issue"
        return DeltaItem(
            external_id=f"{kind}-{number}",
            kind=kind,
            number=int(number),
            title=raw.get("title") or "",
            body=raw.get("body") or "",
            author=(raw.get("user") or {}).get("login") or "unknown",
            url=raw.get("html_url") or "",
            updated_at=raw.get("updated_at") or raw.get("created_at") or "",
            merged=bool((pr or {}).get("merged_at")) if is_pr else False,
        )

    def _raise_for_status(self, resp: httpx.Response) -> None:
        if resp.status_code == 200:
            return
        if resp.status_code == 401:
            raise GitHubAuthError("GitHub rejected the token (401).")
        if resp.status_code in (403, 429):
            remaining = resp.headers.get("X-RateLimit-Remaining")
            retry_after_hdr = resp.headers.get("Retry-After")
            reset_hdr = resp.headers.get("X-RateLimit-Reset")
            is_limit = (resp.status_code == 429 or remaining == "0"
                        or retry_after_hdr is not None)
            if is_limit:
                reset_at = int(reset_hdr) if (reset_hdr or "").isdigit() else None
                retry_after = (int(retry_after_hdr)
                               if (retry_after_hdr or "").isdigit() else None)
                if retry_after is None and reset_at is not None:
                    retry_after = max(0, reset_at - int(time.time()))
                raise GitHubRateLimitError(retry_after=retry_after, reset_at=reset_at)
            raise GitHubError(f"GitHub 403 (not rate limit): {resp.text[:200]}")
        if resp.status_code == 404:
            raise GitHubError(f"repo not found: {self.repo_full_name}")
        raise GitHubError(f"GitHub {resp.status_code}: {resp.text[:200]}")
