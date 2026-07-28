"""Build the memory graph straight from GitHub's structured payloads.

The API already knows who authored a PR, which issue it closes, and which
files it touched — so we read those relations instead of guessing them from
word proximity. Every edge here is a fact from the payload, never an
inference, and every node carries the event's timestamp for recency scoring.

Text extraction (extract.py + curation.py) still runs for prose; this module
covers the part of the graph that structure can answer exactly.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Iterable

from . import config

if TYPE_CHECKING:  # the builder only needs upsert_node/add_relationship
    from .db import TraceDB

logger = logging.getLogger(__name__)

# "Fixes #982", "closes JIRA-77" in a PR body — GitHub only auto-links some of these
_CLOSES_RE = re.compile(
    r"(?:fix(?:e[sd])?|close[sd]?|resolve[sd]?)\s+#(\d+)", re.IGNORECASE
)


@dataclass
class GraphStats:
    nodes: int = 0
    edges: int = 0
    by_relation: dict[str, int] = field(default_factory=dict)

    def count(self, relation: str) -> None:
        self.edges += 1
        self.by_relation[relation] = self.by_relation.get(relation, 0) + 1


def parse_ts(value: str | None) -> int:
    """GitHub ISO-8601 ('2026-07-24T09:12:31Z') -> unix seconds; 0 when absent."""
    if not value:
        return 0
    try:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
    except (ValueError, AttributeError):
        return 0


def _login(actor: dict[str, Any] | None) -> str | None:
    if not actor:
        return None
    return actor.get("login") or actor.get("name")


class GitHubGraphBuilder:
    """Writes typed, timestamped edges from GitHub payloads into the graph.

    Nodes need an embedding, so the caller supplies an embed function — the
    same one curation uses, keeping one vector space across both paths.
    """

    def __init__(self, db: "TraceDB", embed_fn, repo: str) -> None:
        self.db = db
        self.embed = embed_fn
        self.repo = repo
        self.repo_id = f"repo:{repo}"
        self._seen: set[str] = set()

    # nodes -------------------------------------------------------------
    def _node(self, node_id: str, label: str, node_type: str, ts: int = 0) -> str:
        """Upsert once per run; embeddings are the expensive part."""
        if node_id not in self._seen:
            self.db.upsert_node(node_id, label, node_type, self.embed(label), ts=ts)
            self._seen.add(node_id)
        elif ts:
            # already embedded this run — still let a newer event move the clock
            self.db.upsert_node(node_id, label, node_type, self.embed(label), ts=ts)
        return node_id

    def person(self, login: str) -> str:
        return self._node(f"person:{login}", login, "Person")

    def pull_request(self, number: int, title: str, ts: int) -> str:
        return self._node(f"pr:{self.repo}#{number}", f"PR #{number}", "PR", ts)

    def issue(self, number: int, title: str = "", ts: int = 0) -> str:
        return self._node(f"issue:{self.repo}#{number}", f"Issue #{number}", "Ticket", ts)

    def file(self, path: str) -> str:
        return self._node(f"file:{self.repo}:{path}", path, "File")

    def commit(self, sha: str, ts: int) -> str:
        return self._node(f"commit:{self.repo}:{sha[:7]}", sha[:7], "Commit", ts)

    def repository(self) -> str:
        return self._node(self.repo_id, self.repo.split("/")[-1], "Repo")

    # ingestion ---------------------------------------------------------
    def add_pull_request(self, pr: dict[str, Any], stats: GraphStats) -> None:
        number = pr.get("number")
        if number is None:
            return
        ts = parse_ts(pr.get("merged_at") or pr.get("closed_at") or pr.get("created_at"))
        pr_id = self.pull_request(number, pr.get("title") or "", ts)
        repo_id = self.repository()
        self.db.add_relationship(pr_id, repo_id, relation=config.RELATION_TOUCHES, ts=ts)
        stats.count(config.RELATION_TOUCHES)

        author = _login(pr.get("user"))
        if author:
            self.db.add_relationship(
                self.person(author), pr_id, relation=config.RELATION_AUTHORED, ts=ts
            )
            stats.count(config.RELATION_AUTHORED)

        for reviewer in pr.get("requested_reviewers") or []:
            login = _login(reviewer)
            if login:
                self.db.add_relationship(
                    self.person(login), pr_id, relation=config.RELATION_REVIEWED, ts=ts
                )
                stats.count(config.RELATION_REVIEWED)

        # closes/fixes references — the causal link that makes tracing possible
        for ref in set(_CLOSES_RE.findall(pr.get("body") or "")):
            self.db.add_relationship(
                pr_id, self.issue(int(ref)), relation=config.RELATION_RESOLVES, ts=ts
            )
            stats.count(config.RELATION_RESOLVES)

        for f in pr.get("files") or []:
            path = f.get("filename") if isinstance(f, dict) else f
            if path:
                self.db.add_relationship(
                    pr_id, self.file(path), relation=config.RELATION_TOUCHES, ts=ts
                )
                stats.count(config.RELATION_TOUCHES)

    def add_issue(self, issue: dict[str, Any], stats: GraphStats) -> None:
        if issue.get("number") is None or "pull_request" in issue:
            return  # the issues endpoint also returns PRs
        ts = parse_ts(issue.get("created_at"))
        issue_id = self.issue(issue["number"], issue.get("title") or "", ts)
        self.db.add_relationship(
            issue_id, self.repository(), relation=config.RELATION_TOUCHES, ts=ts
        )
        stats.count(config.RELATION_TOUCHES)
        reporter = _login(issue.get("user"))
        if reporter:
            self.db.add_relationship(
                self.person(reporter), issue_id,
                relation=config.RELATION_REPORTED, ts=ts,
            )
            stats.count(config.RELATION_REPORTED)

    def add_commit(self, commit: dict[str, Any], stats: GraphStats) -> None:
        sha = commit.get("sha")
        if not sha:
            return
        inner = commit.get("commit") or {}
        ts = parse_ts((inner.get("author") or {}).get("date"))
        commit_id = self.commit(sha, ts)
        self.db.add_relationship(
            commit_id, self.repository(), relation=config.RELATION_PART_OF, ts=ts
        )
        stats.count(config.RELATION_PART_OF)

        author = _login(commit.get("author")) or (inner.get("author") or {}).get("name")
        if author:
            self.db.add_relationship(
                self.person(author), commit_id,
                relation=config.RELATION_AUTHORED, ts=ts,
            )
            stats.count(config.RELATION_AUTHORED)

        for ref in set(_CLOSES_RE.findall(inner.get("message") or "")):
            self.db.add_relationship(
                commit_id, self.issue(int(ref)),
                relation=config.RELATION_RESOLVES, ts=ts,
            )
            stats.count(config.RELATION_RESOLVES)

    def build(
        self,
        pulls: Iterable[dict[str, Any]] = (),
        issues: Iterable[dict[str, Any]] = (),
        commits: Iterable[dict[str, Any]] = (),
    ) -> GraphStats:
        stats = GraphStats()
        for pr in pulls:
            self.add_pull_request(pr, stats)
        for issue in issues:
            self.add_issue(issue, stats)
        for commit in commits:
            self.add_commit(commit, stats)
        stats.nodes = len(self._seen)
        logger.info(
            "github graph: %d nodes, %d edges %s",
            stats.nodes, stats.edges, stats.by_relation,
        )
        return stats
