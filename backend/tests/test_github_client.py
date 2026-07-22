"""Real GitHub client, network-free, via httpx.MockTransport. Proves pagination,
PR/Issue normalization (incl. merged status), the cursor handoff, rate-limit
handling, and the offline mock fallback.

Run:  python tests/test_github_client.py   (from backend/)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/

import logging
logging.disable(logging.CRITICAL)

import httpx

from worker.ingestion.github_client import (
    GitHubDeltaClient, GitHubRateLimitError,
)


def ok(m): print(f"  [OK] {m}", flush=True)


# --- fake GitHub issues API: two pages, PR (merged) + Issue on p1, PR on p2 ---
_PAGE1 = [
    {"number": 101, "title": "Fix refund NPE", "body": "fixes INFRA-42 in PaymentService",
     "user": {"login": "alice-dev"}, "html_url": "https://gh/acme/pull/101",
     "updated_at": "2026-07-15T10:00:00Z",
     "pull_request": {"merged_at": "2026-07-15T11:00:00Z"}},
    {"number": 58, "title": "BillingService drops events", "body": "INFRA-58 backpressure",
     "user": {"login": "carol-sre"}, "html_url": "https://gh/acme/issues/58",
     "updated_at": "2026-07-16T08:00:00Z"},   # no pull_request => Issue
]
_PAGE2 = [
    {"number": 102, "title": "Add backoff", "body": "retry for BillingService",
     "user": {"login": "bob-ops"}, "html_url": "https://gh/acme/pull/102",
     "updated_at": "2026-07-16T09:30:00Z",
     "pull_request": {"merged_at": None}},     # PR, not merged
]


def paginated_handler(request: httpx.Request) -> httpx.Response:
    page = request.url.params.get("page")
    if page is None or page == "1":
        nxt = str(request.url.copy_set_param("page", "2"))
        return httpx.Response(200, json=_PAGE1, headers={"Link": f'<{nxt}>; rel="next"'})
    return httpx.Response(200, json=_PAGE2)  # page 2: no Link => last page


print("1. Pagination + normalization across two pages")
client = GitHubDeltaClient("acme/payments", cursor=None, token="tok",
                           transport=httpx.MockTransport(paginated_handler))
res = client.fetch_recent_prs_and_commits()
by_num = {i.number: i for i in res.items}
print(f"     fetched {len(res.items)} items: "
      f"{[(i.number, i.kind, i.merged) for i in res.items]}")
assert len(res.items) == 3, res.items                 # both pages merged
assert by_num[101].kind == "PR" and by_num[101].merged is True
assert by_num[58].kind == "Issue" and by_num[58].merged is False
assert by_num[102].kind == "PR" and by_num[102].merged is False   # merged_at null
assert by_num[101].author == "alice-dev"
ok("2 pages followed via Link header; PR/Issue + merged status normalized")

print("2. Cursor handoff = max(updated_at) of the batch")
print(f"     new_cursor = {res.new_cursor}")
assert res.new_cursor == "2026-07-16T09:30:00Z"       # the latest item
ok("new_cursor is the highest updated_at")

print("3. Incremental request sends since= and direction=asc")
seen = {}


def capture_handler(request):
    seen["params"] = dict(request.url.params)
    return httpx.Response(200, json=[])


GitHubDeltaClient("acme/payments", cursor="2026-07-10T00:00:00Z", token="tok",
                  transport=httpx.MockTransport(capture_handler)
                  ).fetch_recent_prs_and_commits()
print(f"     request params: {seen['params']}")
assert seen["params"].get("since") == "2026-07-10T00:00:00Z"
assert seen["params"].get("direction") == "asc"
ok("cursor forwarded as ?since=… with oldest-first paging")

print("4. Rate limit (403, X-RateLimit-Remaining: 0) -> GitHubRateLimitError")
import time as _t
reset = int(_t.time()) + 42


def ratelimit_handler(request):
    return httpx.Response(403, json={"message": "API rate limit exceeded"},
                          headers={"X-RateLimit-Remaining": "0",
                                   "X-RateLimit-Reset": str(reset)})


try:
    GitHubDeltaClient("acme/payments", token="tok",
                      transport=httpx.MockTransport(ratelimit_handler)
                      ).fetch_recent_prs_and_commits()
    raise AssertionError("expected GitHubRateLimitError")
except GitHubRateLimitError as exc:
    print(f"     raised: retry_after~{exc.retry_after}s reset_at={exc.reset_at}")
    assert exc.reset_at == reset
    assert exc.retry_after is not None and 0 <= exc.retry_after <= 42
ok("rate limit raises a catchable exception with reset time (worker can retry)")

print("5. Offline mock fallback (no token, no transport)")
os.environ.pop("GITHUB_TOKEN", None)
os.environ.pop("TRACERAG_GITHUB_MOCK", None)
mock = GitHubDeltaClient("acme/payments", cursor=None).fetch_recent_prs_and_commits()
assert len(mock.items) == 3 and mock.new_cursor
# and it's a genuine no-op once a cursor exists
assert GitHubDeltaClient("acme/payments", cursor=mock.new_cursor
                         ).fetch_recent_prs_and_commits().items == []
ok("no credentials -> deterministic mock batch; cursor -> no-op")

print("\n=====================================================")
print("REAL GITHUB CLIENT PROVEN — pagination, normalization, rate limits, cursor")
print("=====================================================")
