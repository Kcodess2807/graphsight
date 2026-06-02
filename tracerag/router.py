"""Intent-based hybrid router.

Classifies query intent -> sets (alpha, beta) -> runs two streams:
    A) Vector recall   s_v = 1 - cosine_distance
    B) Graph traversal s_g = product of edge confidences along the path
Fuses with S = alpha * s_v + beta * s_g and emits a Cytoscape-ready trace_log.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from . import config
from .db import TraceDB

logger = logging.getLogger(__name__)


@dataclass
class RoutedNode:
    id: str
    label: str | None
    type: str | None
    score_total: float
    score_vector: float
    score_graph: float
    documents: list[dict] = field(default_factory=list)  # mentioning chunks


@dataclass
class RouterResponse:
    query: str
    results: list[RoutedNode]
    trace_log: dict


class TraceRouter:
    """Hybrid retriever: vector + graph, fused by query intent."""

    def __init__(self, db: TraceDB, embed_model: str = config.EMBED_MODEL) -> None:
        self.db = db
        self.embed_model = embed_model
        self._embedder = None   # lazy
        self._groq = None       # lazy

    # --- lazy clients -------------------------------------------------- #
    def _get_embedder(self):
        if self._embedder is None:
            from sentence_transformers import SentenceTransformer

            logger.info("Loading embedder: %s", self.embed_model)
            self._embedder = SentenceTransformer(self.embed_model)
        return self._embedder

    def embed_query(self, text: str) -> list[float]:
        vec = self._get_embedder().encode(text, normalize_embeddings=True)
        return [float(x) for x in vec]

    def _get_groq(self):
        if self._groq is None:
            from groq import Groq

            self._groq = Groq(api_key=config.GROQ_API_KEY)
        return self._groq

    # --- 1. intent classification -------------------------------------- #
    def _classify_intent(self, query: str) -> tuple[float, float, str]:
        q = query.lower()
        if any(m in q for m in config.RELATIONAL_QUERY_MARKERS):
            w = config.ROUTER_WEIGHTS_RELATIONAL
            return w["vector"], w["graph"], "relational"
        if any(m in q for m in config.SEMANTIC_QUERY_MARKERS):
            w = config.ROUTER_WEIGHTS_CONCEPTUAL
            return w["vector"], w["graph"], "semantic"
        return self._classify_intent_llm(query)

    def _classify_intent_llm(self, query: str) -> tuple[float, float, str]:
        prompt = (
            f"Is this query asking for a factual summary (reply SEMANTIC) or "
            f"tracing a sequence of events/people (reply RELATIONAL)?\n\n{query}"
        )
        try:
            resp = self._get_groq().chat.completions.create(
                model=config.GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
            )
            answer = resp.choices[0].message.content.strip().upper()
        except Exception as exc:  # noqa: BLE001 — default to semantic on failure
            logger.warning("Intent LLM failed (%s); defaulting to semantic.", exc)
            answer = "SEMANTIC"
        if "RELATIONAL" in answer:
            w = config.ROUTER_WEIGHTS_RELATIONAL
            return w["vector"], w["graph"], "relational"
        w = config.ROUTER_WEIGHTS_CONCEPTUAL
        return w["vector"], w["graph"], "semantic"

    # --- 2A. vector stream --------------------------------------------- #
    def _vector_stream(
        self, query: str, meta: dict[str, dict]
    ) -> dict[str, float]:
        embedding = self.embed_query(query)
        try:
            hits = self.db.vector_search(embedding, k=config.TOP_K_VECTOR)
        except Exception as exc:  # noqa: BLE001 — empty index, etc.
            logger.debug("vector_search returned nothing (%s)", exc)
            return {}
        scores: dict[str, float] = {}
        for h in hits:
            nid = h["id"]
            if nid is None:
                continue
            scores[nid] = float(h["similarity"])  # already 1 - distance
            meta.setdefault(nid, {"label": h.get("label"), "type": h.get("type")})
        return scores

    # --- 2B. graph stream ---------------------------------------------- #
    def _graph_stream(
        self, vector_scores: dict[str, float], meta: dict[str, dict]
    ) -> tuple[dict[str, float], list[str], list[dict]]:
        seeds = [
            nid for nid, sv in sorted(vector_scores.items(), key=lambda kv: -kv[1])
            if sv >= config.GRAPH_SEED_MIN_SIM
        ][: config.GRAPH_SEED_TOP_N]

        s_g: dict[str, float] = {seed: 1.0 for seed in seeds}
        hops: list[dict] = []

        # Multiplicative BFS: PathScore = product of edge confidences.
        frontier = [(seed, 1.0) for seed in seeds]
        visited: set[str] = set(seeds)
        for _ in range(config.GRAPH_MAX_HOPS):
            next_frontier: list[tuple[str, float]] = []
            for node_id, acc in frontier:
                for nb in self.db.neighbors(node_id, k=config.GRAPH_NEIGHBOR_K):
                    to_id = nb.get("id")
                    if to_id is None:
                        continue
                    conf = float(nb.get("confidence") or 1.0)
                    path_score = acc * conf
                    hops.append({"from_id": node_id, "to_id": to_id, "confidence": conf})
                    meta.setdefault(to_id, {"label": nb.get("label"), "type": nb.get("type")})
                    if path_score > s_g.get(to_id, 0.0):
                        s_g[to_id] = path_score
                    if to_id not in visited:
                        visited.add(to_id)
                        next_frontier.append((to_id, path_score))
            frontier = next_frontier
            if not frontier:
                break
        return s_g, seeds, hops

    def _attach_documents(self, results: list[RoutedNode]) -> None:
        docs_by_entity = self.db.documents_for_entities([r.id for r in results])
        for r in results:
            r.documents = docs_by_entity.get(r.id, [])

    # --- 3. fuse + trace ----------------------------------------------- #
    def route(self, query: str, top_k: int | None = None) -> RouterResponse:
        alpha, beta, intent = self._classify_intent(query)
        meta: dict[str, dict] = {}

        vector_scores = self._vector_stream(query, meta)
        graph_scores, seeds, hops = self._graph_stream(vector_scores, meta)

        results: list[RoutedNode] = []
        for nid in set(vector_scores) | set(graph_scores):
            sv = vector_scores.get(nid, 0.0)
            sg = graph_scores.get(nid, 0.0)
            info = meta.get(nid, {})
            results.append(RoutedNode(
                id=nid,
                label=info.get("label"),
                type=info.get("type"),
                score_total=alpha * sv + beta * sg,
                score_vector=sv,
                score_graph=sg,
            ))
        results.sort(key=lambda r: r.score_total, reverse=True)
        if top_k is not None:
            results = results[:top_k]

        # Augmented Generation: fetch the raw chunk text mentioning the final
        # entities so the LangChain wrapper can pass real context to the LLM.
        self._attach_documents(results)

        trace_log = {
            "intent": {"alpha": alpha, "beta": beta, "type": intent},
            "execution_path": {"vector_seeds": seeds, "graph_hops": hops},
            "metrics": {"total_nodes_evaluated": len(vector_scores) + len(graph_scores)},
        }
        return RouterResponse(query=query, results=results, trace_log=trace_log)
