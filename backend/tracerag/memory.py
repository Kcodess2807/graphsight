"""Agent-written memory: facts an agent stores, replaces and forgets in the graph.

These live beside the facts read from GitHub, marked origin='agent', so the two
can never overwrite each other, and the answer model is always told which is which.
"""

from __future__ import annotations

import re
import time
from typing import Callable, Sequence

from . import config
from .curation import slugify
from .db import TraceDB

_MAX_NAME = 200
_RELATION = re.compile(r"^[A-Z][A-Z0-9_]{0,39}$")


def _relation(raw: str) -> str:
    """'owned by' -> 'OWNED_BY'. Anything that still isn't a plain name is refused."""
    rel = re.sub(r"[^A-Za-z0-9]+", "_", (raw or "").strip()).strip("_").upper()
    if not _RELATION.match(rel):
        raise ValueError(f"relation must be a short name like OWNED_BY, got {raw!r}")
    return rel


def _name(raw: str, what: str) -> str:
    name = " ".join((raw or "").split())
    if not name or len(name) > _MAX_NAME:
        raise ValueError(f"{what} must be 1-{_MAX_NAME} characters")
    return name


class AgentMemory:
    """remember / forget over a TraceDB. embed turns a name into a vector, the same
    function ingest uses, so remembered names land in the same vector space."""

    def __init__(self, db: TraceDB, embed: Callable[[str], Sequence[float]]) -> None:
        self.db = db
        self.embed = embed

    def _find(self, name: str) -> str | None:
        nodes = self.db.find_nodes_by_label(name)
        if not nodes:
            return None
        # prefer the structural node (pr:..., person:...): it holds the typed edges
        return next((n["id"] for n in nodes if ":" in n["id"]), nodes[0]["id"])

    def _node(self, name: str) -> str:
        found = self._find(name)
        if found:
            return found
        node_id = f"mem:{slugify(name)}"
        self.db.upsert_node(node_id, name, "Concept", self.embed(name))
        return node_id

    def remember(
        self, subject: str, relation: str, obj: str, *, source: str, replace: bool = False
    ) -> dict:
        """Store subject -RELATION-> obj. replace=True ends this subject's other facts
        of the same relation: they stop being retrieved but stay in the store."""
        subject, obj = _name(subject, "subject"), _name(obj, "object")
        relation = _relation(relation)
        a, b = self._node(subject), self._node(obj)
        now = int(time.time())
        replaced = self.db.end_memory_edges(a, relation, keep_to_id=b, ts=now) if replace else 0
        self.db.add_memory_edge(a, b, relation, config.AGENT_FACT_WEIGHT, source, now)
        return {"subject": a, "relation": relation, "object": b, "replaced": replaced}

    def forget(self, subject: str, relation: str, obj: str) -> int:
        """Delete a remembered fact, history included. Facts read from GitHub can't
        be forgotten this way. Returns how many edges were removed."""
        subject, obj = _name(subject, "subject"), _name(obj, "object")
        relation = _relation(relation)
        a, b = self._find(subject), self._find(obj)
        if not (a and b):
            return 0
        removed = self.db.delete_memory_edges(a, relation, b)
        self.db.drop_orphan_memory_nodes()
        return removed
