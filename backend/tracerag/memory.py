"""GraphMemory — the embedded entry point.

    mem = GraphMemory("memory.lbug")
    mem.ingest_github("acme/platform", pulls=prs, issues=issues, commits=commits)
    hits = mem.query("who broke checkout yesterday?")

One object owns the store, the embedder, and the router. Everything runs in
this process against a single file; nothing is sent anywhere.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable

from . import config
from .db import TraceDB
from .github_graph import GitHubGraphBuilder, GraphStats
from .router import RouterResponse, TraceRouter

logger = logging.getLogger(__name__)


class GraphMemory:
    def __init__(self, path: str | Path = config.DB_PATH, embed_model: str | None = None):
        self.path = str(path)
        self.db = TraceDB(self.path)
        self.db.init_schema()
        self.router = TraceRouter(self.db, embed_model or config.EMBED_MODEL)
        self._indexed = False

    # ingest ------------------------------------------------------------
    def ingest_github(
        self,
        repo: str,
        pulls: Iterable[dict[str, Any]] = (),
        issues: Iterable[dict[str, Any]] = (),
        commits: Iterable[dict[str, Any]] = (),
    ) -> GraphStats:
        """Typed edges from GitHub payloads — authorship, closes, touches."""
        builder = GitHubGraphBuilder(self.db, self.router._encode, repo)
        stats = builder.build(pulls=pulls, issues=issues, commits=commits)
        self._indexed = False
        return stats

    def ingest_text(self, doc_id: str, text: str, source: str | None = None):
        """Prose path: extract entities, resolve them, store co-occurrence edges."""
        from .curation import CurationEngine
        from .extract import EntityExtractor

        entities = EntityExtractor().extract(text)
        stats = CurationEngine(self.db).ingest(doc_id, text, entities, source=source)
        self._indexed = False
        return stats

    def build_index(self) -> None:
        """(Re)build the HNSW index. Required before the first query after ingest."""
        self.db.build_vector_index()
        self._indexed = True

    # query -------------------------------------------------------------
    def query(self, question: str, top_k: int | None = None) -> RouterResponse:
        if not self._indexed:
            self.build_index()
        return self.router.route(question, top_k)

    def context(self, question: str, top_k: int | None = None) -> str:
        """Retrieved context as a single grounded string, ready for a prompt."""
        return self.router.build_context(self.query(question, top_k).results)

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "GraphMemory":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
