"""Two-tier curation: fast-merge by similarity, deep-merge via LLM, else mint new id."""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from itertools import combinations

from . import config
from .db import TraceDB
from .extract import ExtractedEntity, sliding_window_words

logger = logging.getLogger(__name__)


@dataclass
class IngestStats:
    docs: int = 0
    entities: int = 0
    created: int = 0
    fast_merged: int = 0
    deep_merged_yes: int = 0
    deep_merged_no: int = 0
    ollama_calls: int = 0
    relates_edges: int = 0
    mentions_edges: int = 0

    def merge(self, other: "IngestStats") -> None:
        for f in field_names():
            setattr(self, f, getattr(self, f) + getattr(other, f))


def field_names() -> list[str]:
    return [f.name for f in IngestStats.__dataclass_fields__.values()]


def slugify(text: str) -> str:
    """Canonical readable id, e.g. 'PaymentService Service' -> 'paymentservice-service'."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "entity"


class CurationEngine:
    """Embeds entities, resolves them against the graph, and commits nodes/edges."""

    def __init__(self, db: TraceDB, embed_model: str = config.EMBED_MODEL) -> None:
        self.db = db
        self.embed_model = embed_model
        self._embedder = None
        self._llm = None
        # in-memory dedup index: the DB's HNSW index can't be queried mid-ingest
        self._ids: list[str] = []
        self._labels: list[str] = []
        self._types: list[str] = []
        self._vecs: list[list[float]] = []
        self._index_loaded = False

    def _get_embedder(self):
        if self._embedder is None:
            from sentence_transformers import SentenceTransformer

            logger.info("Loading embedder: %s", self.embed_model)
            self._embedder = SentenceTransformer(self.embed_model)
        return self._embedder

    def _embed(self, text: str) -> list[float]:
        vec = self._get_embedder().encode(text, normalize_embeddings=True)
        return [float(x) for x in vec]

    def _get_llm(self):
        if self._llm is None:
            from .llm import make_client

            self._llm = make_client()
        return self._llm

    def _ensure_index_loaded(self) -> None:
        if self._index_loaded:
            return
        rows = self.db.execute(
            f"MATCH (e:{config.NODE_TABLE}) RETURN e.id AS id, e.label AS label, "
            f"e.type AS type, e.embedding AS emb;"
        ).get_as_df().to_dict("records")
        for r in rows:
            if r["emb"] is not None:
                self._add_to_index(r["id"], r["label"], r["type"], list(r["emb"]))
        self._index_loaded = True
        if rows:
            logger.info("Pre-loaded %d existing nodes into dedup index", len(rows))

    def _add_to_index(self, node_id: str, label: str, ntype: str,
                      embedding: list[float]) -> None:
        self._ids.append(node_id)
        self._labels.append(label)
        self._types.append(ntype)
        self._vecs.append(embedding)

    def ingest(
        self,
        doc_id: str,
        text: str,
        entities: list[ExtractedEntity],
        source: str | None = None,
    ) -> IngestStats:
        stats = IngestStats(docs=1, entities=len(entities))
        if not entities:
            return stats  # no entities -> nothing worth storing for retrieval
        self._ensure_index_loaded()

        resolved = [self._resolve(ent, stats) for ent in entities]
        self._build_chunks_and_edges(doc_id, text, entities, resolved, stats, source)
        return stats

    def _resolve(self, ent: ExtractedEntity, stats: IngestStats) -> str:
        embedding = self._embed(ent.text)
        hits = self._search(embedding)
        top = hits[0] if hits else None

        if top and top["similarity"] >= config.FAST_MERGE_THRESHOLD:
            stats.fast_merged += 1
            return top["id"]

        if top and top["similarity"] >= config.DEEP_MERGE_THRESHOLD:
            stats.ollama_calls += 1
            if self._ask_same_entity(ent.text, top["label"]):
                stats.deep_merged_yes += 1
                return top["id"]
            stats.deep_merged_no += 1

        node_id = self._mint_id(ent)
        self.db.upsert_node(node_id, ent.text, ent.type, embedding)
        self._add_to_index(node_id, ent.text, ent.type, embedding)
        stats.created += 1
        return node_id

    def _search(self, embedding: list[float]) -> list[dict]:
        """Cosine search over the in-memory index (normalized, so cosine == dot)."""
        if not self._vecs:
            return []
        import numpy as np

        mat = np.asarray(self._vecs, dtype=np.float32)
        q = np.asarray(embedding, dtype=np.float32)
        sims = mat @ q
        top = np.argsort(-sims)[: config.CURATION_TOP_K]
        return [
            {"id": self._ids[i], "label": self._labels[i],
             "type": self._types[i], "similarity": float(sims[i])}
            for i in top
        ]

    def _ask_same_entity(self, extracted_text: str, canonical_label: str) -> bool:
        prompt = (
            f"Are '{extracted_text}' and '{canonical_label}' the exact same "
            f"entity? Answer ONLY YES or NO."
        )
        try:
            resp = self._get_llm().chat.completions.create(
                model=config.OPENROUTER_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
            )
            answer = resp.choices[0].message.content.strip().upper()
        except Exception as exc:  # noqa: BLE001 — fail safe: do not merge
            logger.warning("Deep-merge LLM failed (%s); treating as NO.", exc)
            return False
        return answer.startswith("YES")

    def _mint_id(self, ent: ExtractedEntity) -> str:
        base = slugify(f"{ent.text} {ent.type}")
        if not self.db.node_exists(base):
            return base
        # slug collision between distinct entities: disambiguate with a short text hash
        suffix = hashlib.sha1(ent.text.encode()).hexdigest()[:6]
        candidate = f"{base}-{suffix}"
        n = 2
        while self.db.node_exists(candidate):
            candidate = f"{base}-{suffix}-{n}"
            n += 1
        return candidate

    def _build_chunks_and_edges(
        self,
        doc_id: str,
        text: str,
        entities: list[ExtractedEntity],
        resolved: list[str],
        stats: IngestStats,
        source: str | None = None,
    ) -> None:
        seen_pairs: set[tuple[str, str]] = set()
        for idx, win in enumerate(sliding_window_words(text)):
            win_end = win.offset + len(win.text)
            members = [
                resolved[i]
                for i, e in enumerate(entities)
                if e.start >= win.offset and e.end <= win_end
            ]
            if not members:
                continue  # don't store chunks that surface no entities

            # path keeps source provenance (PR url when given, else doc id) for citation
            chunk_id = f"{doc_id}#w{idx}"
            self.db.upsert_document(chunk_id, content=win.text, path=source or doc_id)

            for entity_id in members:
                self.db.add_mention(chunk_id, entity_id)
                stats.mentions_edges += 1

            for a, b in combinations(sorted(set(members)), 2):
                if a == b or (a, b) in seen_pairs:
                    continue
                seen_pairs.add((a, b))
                self.db.add_relationship(a, b)
                stats.relates_edges += 1
