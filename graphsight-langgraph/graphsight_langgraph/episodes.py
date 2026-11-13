"""Episodic memory: past runs in the history dir, found by what they were asked."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from ._text import tokens

_MIN_MATCH = 0.5  # below this the questions share too little to be the same task


@dataclass
class Episode:
    """One past run, reduced to what a later run can reuse."""

    file: str
    query: str
    answer: str
    outcome: str
    score: float  # lexical match between this query and the new one (0..1)
    computed_at: str = ""
    # labels the answer overlapped: what the past run actually leaned on
    used: list[str] = field(default_factory=list)

    def render(self) -> str:
        sources = f"\nSources it used: {', '.join(self.used)}" if self.used else ""
        return f"Earlier question: {self.query}\nEarlier answer: {self.answer}{sources}"


def _load(path: Path) -> Optional[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None  # a history dir can hold anything; skip what isn't readable
    return data if isinstance(data, dict) and data.get("answer") and data.get("query") else None


def recall(
    query: str,
    k: int = 3,
    dir: Union[str, Path, None] = None,
    outcome: str = "success",
) -> list[Episode]:
    """The k past runs closest to query, best first. Only runs labelled with
    outcome are candidates, so a failed or unjudged run can't teach the next one."""
    # ponytail: linear scan with a lexical match. Fine for hundreds of runs; swap
    # in embeddings when paraphrased questions start missing.
    root = Path(dir or os.environ.get("GRAPHSIGHT_DIR") or ".graphsight")
    wanted = tokens(query)
    if not wanted or not root.is_dir():
        return []

    found: dict[str, Episode] = {}
    for path in root.glob("*.json"):
        data = _load(path)
        if data is None or data.get("outcome") != outcome:
            continue
        asked = tokens(data["query"])
        if not asked:
            continue
        score = round(len(wanted & asked) / min(len(wanted), len(asked)), 3)
        if score < _MIN_MATCH:
            continue
        nodes = (data.get("graph") or {}).get("nodes") or []
        episode = Episode(
            file=path.name,
            query=data["query"],
            answer=data["answer"],
            outcome=data["outcome"],
            score=score,
            computed_at=data.get("computedAt") or "",
            # earlier episodes stay out, or memories start citing memories
            used=[
                n["label"] for n in nodes
                if n.get("active") and (n.get("meta") or {}).get("answerOverlap")
                and not str(n.get("id")).startswith("episode:")
            ],
        )
        # the same question run twice is one memory, or recall feeds on its own copies
        kept = found.get(episode.query)
        if kept is None or episode.computed_at > kept.computed_at:
            found[episode.query] = episode
    return sorted(found.values(), key=lambda e: (e.score, e.computed_at), reverse=True)[:k]


class EpisodeRetriever(BaseRetriever):
    """recall() as a retriever, so episodes are traced like any other evidence."""

    k: int = 3
    dir: Optional[str] = None

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        return [
            Document(
                page_content=e.render(),
                metadata={
                    "id": f"episode:{e.file}",
                    "label": f"Past run: {e.query}",
                    "kind": "episode",
                    "score": e.score,
                },
            )
            for e in recall(query, k=self.k, dir=self.dir)
        ]
