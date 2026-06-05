"""Two-tier curation engine.

For each extracted entity:
    sim >= FAST_MERGE_THRESHOLD (0.92)              -> Fast Mode: reuse existing id
    DEEP_MERGE_THRESHOLD (0.85) <= sim < 0.92       -> ask the LLM YES/NO
    sim <  DEEP_MERGE_THRESHOLD                      -> mint a new slug id

Edges: Document -[MENTIONS]-> every entity; Entity -[RELATES_TO]-> Entity only
for entities co-occurring inside the same sliding window.
"""

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
    """canonical, terminal/UI-readable id, e.g. 'PaymentService' + 'Service'
    -> 'paymentservice-service'."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "entity"


class CurationEngine:
    """Embeds entities, resolves them against the graph, and commits nodes/edges."""

    def __init__(self, db: TraceDB, embed_model: str = config.EMBED_MODEL) -> None:
        self.db = db
        self.embed_model = embed_model
        self._embedder = None        # lazy
        self._llm = None             # lazy (OpenRouter)
        # In-memory dedup index. The DB's HNSW index is static (can't be queried
        # mid-ingest while embeddings are still being written), so curation does
        # its own cosine search over normalized embeddings here. Pre-loaded with
        # existing nodes so re-ingests dedup against prior data too.
        self._ids: list[str] = []
        self._labels: list[str] = []
        self._types: list[str] = []
        self._vecs: list[list[float]] = []
        self._index_loaded = False

    # --- lazy clients -------------------------------------------------- #
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

    # --- in-memory dedup index ----------------------------------------- #
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

    # --- public API ---------------------------------------------------- #
    def ingest(
        self,
        doc_id: str,
        text: str,
        entities: list[ExtractedEntity],
        source: str | None = None,
    ) -> IngestStats:
        stats = IngestStats(docs=1, entities=len(entities))
        if not entities:
            return stats  # no entities -> no chunk worth storing for retrieval
        self._ensure_index_loaded()

        # 1. Resolve each entity to a canonical node id (committing new nodes).
        resolved = [self._resolve(ent, stats) for ent in entities]

        # 2. Per sliding window: store the chunk text as a Document node, link
        #    MENTIONS to its entities, and RELATES_TO between co-occurring ones.
        #    `source` (e.g. a GitHub PR URL) is stored as the Document path so
        #    the UI can deep-link back to the original; falls back to doc_id.
        self._build_chunks_and_edges(doc_id, text, entities, resolved, stats, source)
        return stats

    # --- entity resolution (the two-tier decision) -------------------- #
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

        # New node.
        node_id = self._mint_id(ent)
        self.db.upsert_node(node_id, ent.text, ent.type, embedding)
        self._add_to_index(node_id, ent.text, ent.type, embedding)
        stats.created += 1
        return node_id

    def _search(self, embedding: list[float]) -> list[dict]:
        """Cosine search over the in-memory index (embeddings are normalized,
        so cosine == dot product). Returns hits sorted most-similar first."""
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
        # Slug collision between genuinely distinct entities: disambiguate
        # deterministically with a short hash of the surface text.
        suffix = hashlib.sha1(ent.text.encode()).hexdigest()[:6]
        candidate = f"{base}-{suffix}"
        n = 2
        while self.db.node_exists(candidate):
            candidate = f"{base}-{suffix}-{n}"
            n += 1
        return candidate

    # --- chunk documents + edges -------------------------------------- #
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

            # The Document node represents this specific chunk; path keeps the
            # source provenance (a GitHub PR URL when given, else the doc id) so
            # retrieval can cite — and the UI can deep-link to — where text came from.
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
