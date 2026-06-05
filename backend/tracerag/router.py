"""Intent-based hybrid router.

Classifies query intent -> sets (alpha, beta) -> runs two streams:
    A) Vector recall   s_v = 1 - cosine_distance
    B) Graph traversal s_g = product of edge confidences along the path
Fuses with S = alpha * s_v + beta * s_g and emits a Cytoscape-ready trace_log.
"""

from __future__ import annotations

import logging
import time
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
        self._embedder = None    # lazy
        self._llm = None         # lazy (OpenRouter — curation/deep-merge)
        self._intent_llm = None  # lazy ((client, model) — Groq if available)
        self._extractor = None   # lazy (query-side entity linking)

    def warm(self) -> None:
        """Eagerly load the embedder + spaCy extractor so the FIRST user query
        doesn't eat the one-time model-load cost (~5s for spaCy alone). Called
        from the API lifespan; safe to call repeatedly (loaders are idempotent).
        The intent LLM is intentionally NOT warmed — it's a network call, only
        fires on keyword-less queries, and defaults to semantic on timeout."""
        self._get_embedder().encode("warmup", normalize_embeddings=True)
        try:
            self._get_extractor().extract("warmup")
        except Exception as exc:  # noqa: BLE001 — never let warmup break boot
            logger.debug("extractor warmup skipped (%s)", exc)

    # --- lazy clients -------------------------------------------------- #
    def _get_embedder(self):
        if self._embedder is None:
            from sentence_transformers import SentenceTransformer

            logger.info("Loading embedder: %s", self.embed_model)
            self._embedder = SentenceTransformer(self.embed_model)
        return self._embedder

    def _get_extractor(self):
        if self._extractor is None:
            from .extract import EntityExtractor

            # Query-side linking needs only the deterministic spaCy EntityRuler
            # (ticket/PR/service matches) — NOT the heavy GLiNER transformer,
            # which would waste ~750MB per request and crash under concurrent
            # queries (os error 1455). GLiNER stays at ingest time.
            self._extractor = EntityExtractor(prefer_gliner=False)
        return self._extractor

    def _link_query_entities(self, query: str, meta: dict[str, dict]) -> list[str]:
        """Deterministic seeds: extract entities from the query and look up
        their exact matching graph nodes by label (tickets, PRs, services)."""
        ids: list[str] = []
        try:
            entities = self._get_extractor().extract(query)
        except Exception as exc:  # noqa: BLE001 — never let linking break a query
            logger.debug("query entity extraction failed (%s)", exc)
            return ids
        for ent in entities:
            for node in self.db.find_nodes_by_label(ent.text):
                nid = node["id"]
                meta.setdefault(nid, {"label": node["label"], "type": node["type"]})
                ids.append(nid)
        return list(dict.fromkeys(ids))  # dedupe, preserve order

    def embed_query(self, text: str) -> list[float]:
        vec = self._get_embedder().encode(text, normalize_embeddings=True)
        return [float(x) for x in vec]

    def _get_llm(self):
        if self._llm is None:
            from .llm import make_client

            self._llm = make_client()
        return self._llm

    def _get_intent_llm(self) -> tuple[object, str]:
        """Lazily build the intent (client, model) — Groq when available, else
        OpenRouter. Cached so we don't rebuild the client per query."""
        if self._intent_llm is None:
            from .llm import make_intent_client

            self._intent_llm = make_intent_client()
        return self._intent_llm

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
            "Reply with ONE word — RELATIONAL if the query traces a sequence of "
            "events/people/links, else SEMANTIC.\n\n" + query
        )
        try:
            # Tiny output + short timeout: we only need one token, and a slow
            # router call must never dominate latency — fail fast to SEMANTIC.
            # Groq (when configured) returns this in ~200-400ms vs ~4.5s on the
            # OpenRouter free tier; the client/model are chosen in make_intent_client.
            client, model = self._get_intent_llm()
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=4,
                timeout=6,
            )
            answer = (resp.choices[0].message.content or "").strip().upper()
        except Exception as exc:  # noqa: BLE001 — default to semantic on failure
            logger.warning("Intent LLM failed (%s); defaulting to semantic.", exc)
            answer = "SEMANTIC"
        if "RELATIONAL" in answer:
            w = config.ROUTER_WEIGHTS_RELATIONAL
            return w["vector"], w["graph"], "relational"
        w = config.ROUTER_WEIGHTS_CONCEPTUAL
        return w["vector"], w["graph"], "semantic"

    # --- 2A. vector stream --------------------------------------------- #
    def _vector_hits(
        self, query: str, k: int, meta: dict[str, dict]
    ) -> list[tuple[str, float]]:
        """Top-k vector hits as an ordered (id, similarity) list, best first."""
        embedding = self.embed_query(query)
        try:
            hits = self.db.vector_search(embedding, k=k)
        except Exception as exc:  # noqa: BLE001 — empty index, etc.
            logger.debug("vector_search returned nothing (%s)", exc)
            return []
        out: list[tuple[str, float]] = []
        for h in hits:
            nid = h["id"]
            if nid is None:
                continue
            meta.setdefault(nid, {"label": h.get("label"), "type": h.get("type")})
            out.append((nid, float(h["similarity"])))  # similarity = 1 - distance
        return out

    # --- 2B. graph stream ---------------------------------------------- #
    def _graph_stream(
        self, seeds: list[str], meta: dict[str, dict]
    ) -> tuple[dict[str, float], list[dict]]:
        s_g: dict[str, float] = {seed: 1.0 for seed in seeds}
        hops: list[dict] = []

        # Multiplicative BFS: PathScore = product of edge confidences. Each hop
        # expands the ENTIRE frontier in ONE batched DB query (see
        # db.expand_frontier) — the super-node degree check and per-node top-k
        # are applied there, so a 2-hop walk costs at most 2 round-trips total
        # rather than 2 per node.
        frontier: dict[str, float] = {seed: 1.0 for seed in seeds}
        visited: set[str] = set(seeds)
        for _ in range(config.GRAPH_MAX_HOPS):
            if not frontier:
                break
            expanded = self.db.expand_frontier(
                list(frontier), config.GRAPH_NEIGHBOR_K, config.MAX_DEGREE
            )
            next_frontier: dict[str, float] = {}
            for node_id, acc in frontier.items():
                for nb in expanded.get(node_id, []):
                    to_id = nb["id"]
                    conf = nb["confidence"]
                    path_score = acc * conf
                    hops.append({"from_id": node_id, "to_id": to_id, "confidence": conf})
                    meta.setdefault(to_id, {"label": nb["label"], "type": nb["type"]})
                    if path_score > s_g.get(to_id, 0.0):
                        s_g[to_id] = path_score
                    if to_id not in visited:
                        visited.add(to_id)
                        # keep the best path score for the next hop's frontier
                        if path_score > next_frontier.get(to_id, 0.0):
                            next_frontier[to_id] = path_score
            frontier = next_frontier
        return s_g, hops

    def _attach_documents(self, results: list[RoutedNode]) -> None:
        docs_by_entity = self.db.documents_for_entities([r.id for r in results])
        for r in results:
            r.documents = docs_by_entity.get(r.id, [])

    def build_context(self, results: list[RoutedNode]) -> str:
        """Assemble the final, globally-deduplicated context for the LLM.

        Two concerns are solved together:

        * **Redundancy Trap** — each chunk (keyed by doc id) is emitted once;
          a chunk re-surfaced by another arm becomes a 1-line trace marker.
        * **Truncation priority** — the context is split into a high-value
          ``SYSTEM TRACES`` block (entity identities + relationship markers,
          all cheap) placed FIRST, then a ``DOCUMENT CHUNKS`` block of the heavy
          ~300-word text. If the consumer truncates at N chars, the graph
          traversal facts survive intact and only fuzzy text is lost.
        """
        seen_chunk_ids: set[str] = set()
        graph_traces: list[str] = []   # cheap structural facts -> top
        text_chunks: list[str] = []    # heavy fuzzy text -> bottom (truncated first)

        for node in results:
            label = node.label or node.id
            ntype = node.type or "Unknown"
            graph_traces.append(f"- {label} ({ntype})")
            for d in node.documents:
                cid = d.get("doc_id")
                text = (d.get("content") or "").strip()
                if not text:
                    continue
                if cid not in seen_chunk_ids:
                    seen_chunk_ids.add(cid)
                    text_chunks.append(f"[{label}] {text}")
                else:
                    # Duplicate chunk: keep the relationship fact, drop the text.
                    graph_traces.append(f"  [Trace: {label} ({ntype}) -> {cid}]")

        sections: list[str] = []
        if graph_traces:
            sections.append("SYSTEM TRACES:\n" + "\n".join(graph_traces))
        if text_chunks:
            sections.append("DOCUMENT CHUNKS:\n" + "\n\n".join(text_chunks))
        return "\n\n".join(sections)

    # --- 3. dynamic throttle + fuse + trace ---------------------------- #
    def route(self, query: str, top_k: int | None = None) -> RouterResponse:
        # --- profiling: wall-clock per phase, logged at the end ----------- #
        t0 = time.perf_counter()
        alpha, beta, intent = self._classify_intent(query)
        t_intent = time.perf_counter()
        total_k = top_k if top_k is not None else config.TOP_K_VECTOR
        meta: dict[str, dict] = {}

        # A pool of vector hits provides fuzzy graph seeds and the candidate
        # pool we later throttle for fusion.
        pool = self._vector_hits(query, config.TOP_K_VECTOR, meta)
        t_vector = time.perf_counter()

        # Seeds = deterministic query-side entity links FIRST (exact ticket/PR/
        # service matches), then fuzzy cosine seeds (sim >= GRAPH_SEED_MIN_SIM).
        linked_seeds = self._link_query_entities(query, meta)
        fuzzy_seeds = [
            nid for nid, sv in sorted(pool, key=lambda kv: -kv[1])
            if sv >= config.GRAPH_SEED_MIN_SIM
        ][: config.GRAPH_SEED_TOP_N]
        seeds = list(dict.fromkeys(linked_seeds + fuzzy_seeds))  # dedupe, linked first

        # Fallback: a relational query whose vector hits all fell below
        # GRAPH_SEED_MIN_SIM (and named no exact entity) would otherwise leave
        # the graph arm idle at 0 hops despite high beta. Anchor traversal on
        # the strongest vector hits so the graph arm actually contributes.
        if not seeds and pool:
            seeds = [
                nid for nid, _ in sorted(pool, key=lambda kv: -kv[1])
            ][: config.GRAPH_SEED_TOP_N]
        t_seeds = time.perf_counter()

        # Graph traversal — count the connected nodes it discovers.
        graph_scores, hops = self._graph_stream(seeds, meta)
        t_graph = time.perf_counter()
        seed_set = set(seeds)
        graph_hits = sum(1 for nid in graph_scores if nid not in seed_set)

        # Dynamic throttle: the more high-precision graph hits, the fewer bulky
        # vector chunks we pull. vector_k = max(2, total_k - graph_hits).
        vector_k = max(2, total_k - graph_hits)
        vector_scores = dict(pool[:vector_k])

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
        results = results[:total_k]

        # Augmented Generation: fetch the raw chunk text mentioning the final
        # entities so the LangChain wrapper can pass real context to the LLM.
        self._attach_documents(results)
        t_docs = time.perf_counter()

        logger.info(
            "route timings (ms): intent=%.0f vector=%.0f seeds=%.0f graph=%.0f "
            "assemble=%.0f | TOTAL=%.0f  [intent=%s seeds=%d hops=%d]",
            (t_intent - t0) * 1000, (t_vector - t_intent) * 1000,
            (t_seeds - t_vector) * 1000, (t_graph - t_seeds) * 1000,
            (t_docs - t_graph) * 1000, (t_docs - t0) * 1000,
            intent, len(seeds), len(hops),
        )

        trace_log = {
            "intent": {"alpha": alpha, "beta": beta, "type": intent},
            "execution_path": {
                "linked_seeds": linked_seeds,   # deterministic query-entity matches
                "vector_seeds": seeds,           # full seed set (linked + fuzzy)
                "graph_hops": hops,
            },
            "metrics": {
                "graph_hits": graph_hits,
                "vector_k": vector_k,
                "total_nodes_evaluated": len(vector_scores) + len(graph_scores),
            },
        }
        return RouterResponse(query=query, results=results, trace_log=trace_log)
