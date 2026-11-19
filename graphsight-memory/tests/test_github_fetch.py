"""GitHub fetch filters and paging. Network calls are stubbed."""
from graphsight_memory import github as gh

PULL = {"number": 412, "title": "Fix token refresh", "merged_at": "2026-07-27T10:00:00Z",
        "user": {"login": "vishal"}, "body": "Fixes #77"}


def test_only_merged_prs_are_kept(monkeypatch):
    pages = [[{"number": 1, "merged_at": "2026-01-01T00:00:00Z"},
              {"number": 2, "merged_at": None}], []]
    monkeypatch.setattr(gh, "_get", lambda *a, **k: pages.pop(0))
    assert [p["number"] for p in gh.fetch_merged_prs("acme/api", 10, None)] == [1]


def test_the_issues_endpoint_drops_pull_requests(monkeypatch):
    pages = [[{"number": 5}, {"number": 6, "pull_request": {"url": "..."}}], []]
    monkeypatch.setattr(gh, "_get", lambda *a, **k: pages.pop(0))
    assert [i["number"] for i in gh.fetch_issues("acme/api", 10, None)] == [5]


def test_zero_limits_skip_the_request_entirely(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("should not have called the API")

    monkeypatch.setattr(gh, "_get", boom)
    assert gh.fetch_issues("acme/api", 0, None) == []
    assert gh.fetch_commits("acme/api", 0, None) == []


def test_a_failed_file_fetch_does_not_abort_the_run(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("GitHub API 403")

    monkeypatch.setattr(gh, "_get", boom)
    prs = [dict(PULL)]
    gh.attach_pr_details("acme/api", prs, None, files=True)  # must not raise
    assert "files" not in prs[0]


def test_paging_stops_on_a_short_page(monkeypatch):
    """A short page is the last one. Without this every per-PR fetch paid for an
    extra round trip just to see an empty list."""
    calls = []

    def fake_get(url, token, params=None):
        calls.append(params["page"])
        return [{"number": i} for i in range(30)]  # < per_page

    monkeypatch.setattr(gh, "_get", fake_get)
    assert len(gh.fetch_commits("acme/api", 500, None)) == 30
    assert calls == [1]


def test_a_wide_pr_file_list_is_not_truncated_at_one_page(monkeypatch):
    """The files endpoint caps at 100 per page; a big refactor must still be
    fully read rather than silently losing everything past the first hundred."""
    pages = {1: [{"filename": f"a{i}.py"} for i in range(100)],
             2: [{"filename": f"b{i}.py"} for i in range(40)]}

    monkeypatch.setattr(gh, "_get",
                        lambda url, token, params=None: pages.get(params["page"], []))
    prs = [dict(PULL)]
    gh.attach_pr_details("acme/api", prs, None, files=True)
    assert len(prs[0]["files"]) == 140
