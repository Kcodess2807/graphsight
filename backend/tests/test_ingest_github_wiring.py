"""The live GitHub path actually reaches GitHubGraphBuilder.

The builder has its own unit tests against fake payloads; these check the
wiring — that ingest_github fetches the extra endpoints, filters them right,
and lands typed edges in a real store. Network calls are stubbed.
"""
import sys
from pathlib import Path

import pytest

pytest.importorskip("ladybug", reason="LadybugDB driver not installed")
pytest.importorskip("requests")
pytest.importorskip("tqdm")

_BACKEND = Path(__file__).resolve().parents[1]
for p in (_BACKEND, _BACKEND / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import ingest_github as gh                          # noqa: E402
from tracerag import config                         # noqa: E402
from tracerag.db import TraceDB                     # noqa: E402

EMBED = [0.0] * config.EMBED_DIM
EMBED[0] = 1.0

PULL = {
    "number": 412, "title": "Fix token refresh", "merged_at": "2026-07-27T10:00:00Z",
    "html_url": "https://github.com/acme/api/pull/412",
    "user": {"login": "vishal"},
    "requested_reviewers": [{"login": "arush"}],
    "body": "Fixes #77",
}
ISSUE = {"number": 77, "title": "Sessions drop", "created_at": "2026-07-20T08:00:00Z",
         "user": {"login": "utsav"}}
COMMIT = {"sha": "abc1234def", "author": {"login": "vishal"},
          "commit": {"message": "hotfix, closes #77",
                     "author": {"date": "2026-07-27T09:00:00Z"}}}
FILES = [{"filename": "auth/session.py"}]


# --- fetch filters --------------------------------------------------------

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
    gh.attach_pr_files("acme/api", prs, None)  # must not raise
    assert "files" not in prs[0]


# --- the wiring -----------------------------------------------------------

@pytest.fixture
def ingested(tmp_path, monkeypatch):
    monkeypatch.setattr(gh, "fetch_merged_prs", lambda *a, **k: [dict(PULL)])
    monkeypatch.setattr(gh, "fetch_issues", lambda *a, **k: [ISSUE])
    monkeypatch.setattr(gh, "fetch_commits", lambda *a, **k: [COMMIT])
    monkeypatch.setattr(gh, "attach_pr_files",
                        lambda repo, prs, token: [pr.update(files=FILES) for pr in prs])
    # stub the embedder — this test is about wiring, not vectors
    monkeypatch.setattr(gh.CurationEngine, "embed", lambda self, text: list(EMBED))

    db_path = tmp_path / "acme.lbug"
    args = gh.parse_args(["--repo", "acme/api", "--no-text",
                          "--issues", "5", "--commits", "5", "--files"])
    gh.ingest_repo("acme/api", db_path, args, None, None)

    db = TraceDB(db_path, pool_size=1)
    yield db
    db.close()


def edges(db) -> set[tuple[str, str, str]]:
    rows = db._fetch(
        f"MATCH (a:{config.NODE_TABLE})-[r:{config.REL_TABLE}]->"
        f"(b:{config.NODE_TABLE}) "
        f"RETURN a.id AS src, b.id AS dst, r.relation AS relation;")
    return {(r["src"], r["dst"], r["relation"]) for r in rows}


def test_live_path_writes_every_relation_kind(ingested):
    seen = edges(ingested)
    assert ("person:vishal", "pr:acme/api#412", config.RELATION_AUTHORED) in seen
    assert ("person:arush", "pr:acme/api#412", config.RELATION_REVIEWED) in seen
    assert ("pr:acme/api#412", "issue:acme/api#77", config.RELATION_RESOLVES) in seen
    assert ("pr:acme/api#412", "file:acme/api:auth/session.py",
            config.RELATION_TOUCHES) in seen
    assert ("person:utsav", "issue:acme/api#77", config.RELATION_REPORTED) in seen
    assert ("commit:acme/api:abc1234", "repo:acme/api",
            config.RELATION_PART_OF) in seen
    assert ("commit:acme/api:abc1234", "issue:acme/api#77",
            config.RELATION_RESOLVES) in seen


def test_the_pr_is_dated_by_its_merge_not_by_now(ingested):
    from tracerag.github_graph import parse_ts

    rows = ingested._fetch(
        f"MATCH (e:{config.NODE_TABLE} {{id:'pr:acme/api#412'}}) RETURN e.ts AS ts;")
    assert rows[0]["ts"] == parse_ts(PULL["merged_at"])


def test_no_relation_is_left_untyped(ingested):
    relations = {r for _, _, r in edges(ingested)}
    assert config.RELATION_CO_OCCURS not in relations, (
        "--no-text ran, so every edge should come from structure")


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
