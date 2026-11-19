"""Memory: the one class most callers need."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from . import config
from .db import TraceDB
from .github import attach_pr_details, fetch_commits, fetch_issues, fetch_merged_prs, prune
from .github_graph import GitHubGraphBuilder
from .memory import AgentMemory, _relation
from .relations import RELATIONS
from .router import TraceRouter

_REMEMBERED = re.compile(r" \(remembered, source: (.*)\)$")


@dataclass(frozen=True)
class Fact:
    """One relation the answer model is given, e.g. "PR #7 RESOLVES Issue #9"."""
    text: str
    remembered: bool          # an agent wrote it; False means read from GitHub
    source: str | None = None


@dataclass
class Recall:
    question: str
    facts: list[Fact]
    text: str                 # facts plus evidence, ready to put in a prompt
    results: list = field(repr=False)
    trace: dict = field(repr=False)

    def __str__(self) -> str:
        return self.text


class Memory:
    """A project's memory in one local file: GitHub history as a typed graph,
    plus the facts an agent was told, each with its source.

        mem = Memory("team.lbug")
        mem.sync_github("org/repo")
        mem.remember("src/x.py", "OWNED_BY", "payments team", source="standup")
        print(mem.recall("who should review a change to src/x.py?"))
    """

    def __init__(self, path: str | Path = "memory.lbug", *,
                 embed: Callable[[str], Sequence[float]] | None = None,
                 relations: Collection[str] | None = tuple(RELATIONS)) -> None:
        self.db = TraceDB(path)
        self.db.init_schema()
        self.router = TraceRouter(self.db)
        if embed is not None:
            self.router._embedder = embed
        self.relations = frozenset(relations) if relations else None
        self._agent = AgentMemory(self.db, self.router.embed_query)

    # reading GitHub ---------------------------------------------------
    def sync_github(self, repo: str, *, prs: int = 50, issues: int = 50, commits: int = 0,
                    token: str | None = None, details: bool = True) -> dict:
        """Read merged PRs, issues and commits into the graph. details fetches each
        PR's files and reviews: one extra request per PR, but it is what lets a
        question reach the person behind a file."""
        token = token or os.getenv("GITHUB_TOKEN")
        pulls = fetch_merged_prs(repo, prs, token)
        attach_pr_details(repo, pulls, token, files=details, reviews=details)
        return self.load(repo, prune(pulls, fetch_issues(repo, issues, token),
                                     fetch_commits(repo, commits, token)))

    def load(self, repo: str, snapshot: dict | str | Path) -> dict:
        """Build from a saved snapshot: a dict, or a JSON file of {pulls, issues, commits}."""
        if not isinstance(snapshot, dict):
            snapshot = json.loads(Path(snapshot).read_text(encoding="utf-8"))
        stats = GitHubGraphBuilder(self.db, self.router.embed_query, repo).build(
            pulls=snapshot.get("pulls", ()), issues=snapshot.get("issues", ()),
            commits=snapshot.get("commits", ()))
        self.db.build_vector_index()
        return {"nodes": stats.nodes, "edges": stats.edges, "by_relation": dict(stats.by_relation)}

    # writing what the agent was told ----------------------------------
    def _check(self, relation: str) -> str:
        rel = _relation(relation)
        if self.relations and rel not in self.relations:
            raise ValueError(f"unknown relation {rel}; use one of {sorted(self.relations)}, "
                             "or open Memory(..., relations=None) to allow any")
        return rel

    def remember(self, subject: str, relation: str, obj: str, *, source: str,
                 replace: bool = False) -> dict:
        """Store SUBJECT RELATION OBJECT. replace=True ends the subject's other facts
        of this relation: they stop being recalled and stay as history."""
        return self._agent.remember(subject, self._check(relation), obj,
                                    source=source, replace=replace)

    def retract(self, subject: str, relation: str) -> int:
        """End every live fact of this relation on subject, with nothing in its place."""
        return self._agent.retract(subject, self._check(relation))

    def forget(self, subject: str, relation: str, obj: str) -> int:
        """Delete a remembered fact, history included. GitHub facts can't be forgotten."""
        return self._agent.forget(subject, _relation(relation), obj)

    def learn(self, text: str, *, source: str, llm=None, model: str | None = None) -> list[dict]:
        """Have an LLM pull facts out of plain text and remember them. Needs an
        OpenAI-compatible client, or OPENROUTER_API_KEY and pip install openai."""
        if llm is None:
            if not config.OPENROUTER_API_KEY:
                raise RuntimeError("learn() needs an LLM: pass llm=, or set OPENROUTER_API_KEY")
            from .llm import make_client
            llm = make_client()
        return self._agent.learn(text, llm, model or config.OPENROUTER_MODEL, source=source,
                                 relations=self.relations)

    # reading it back --------------------------------------------------
    def recall(self, question: str, k: int | None = None) -> Recall:
        """The facts and evidence for a question. str(recall) goes in a prompt."""
        res = self.router.route(question, top_k=k or config.TOP_K_VECTOR)
        facts = []
        for line in res.facts:
            m = _REMEMBERED.search(line)
            facts.append(Fact(_REMEMBERED.sub("", line), True, m.group(1)) if m else Fact(line, False))
        return Recall(question, facts, self.router.build_context(res.results, res.facts),
                      res.results, res.trace_log)

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "Memory":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
