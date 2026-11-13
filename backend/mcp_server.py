"""MCP server: semantic tools over the TraceRAG hybrid engine. Read-only by default;
remember and forget exist only when TRACERAG_MCP_WRITE_TOKEN is set.

This is the agent-facing surface of TraceRAG. It exposes the retrieval engine to
IDE agents (Cursor, Claude Desktop, etc.) over the Model Context Protocol as a
*small set of typed tools* — deliberately NOT raw Cypher. Every tool routes
THROUGH the hybrid router / graph traversal, so the agent inherits vector
disambiguation, confidence-decayed BFS and source provenance for free, and can
never hand-write a query that escapes the hop / degree / length guards or reads
outside its own graph. The moat (hybrid retrieval) stays server-side; the agent
only gets to pick a verb.

Transport: mounted as a Streamable-HTTP ASGI sub-app on the FastAPI instance
(see api.py). `stateless_http=True` — no session affinity, so it fits the
fungible-pod serving model directly.

Every tool reads the warm graph through `get_current_tenant()`, live, so the
tools follow `/api/graphs/switch` automatically.
"""

from __future__ import annotations

import asyncio
import hmac
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Callable, Optional

from tracerag import config
from tracerag.db import TraceDB
from tracerag.memory import AgentMemory
from tracerag.router import TraceRouter

logger = logging.getLogger("tracerag.mcp")

# The MCP SDK is an optional dependency: if it isn't installed the API still
# boots, just without the /mcp surface (mirrors how history/Sentry are optional).
try:
    from mcp.server.fastmcp import FastMCP

    _MCP_AVAILABLE = True
except Exception as exc:  # noqa: BLE001
    FastMCP = None  # type: ignore
    _MCP_AVAILABLE = False
    logger.info("MCP SDK not installed (%s); /mcp surface disabled.", exc)


@dataclass
class Tenant:
    """The graph a tool call operates on: the one warm local graph."""

    router: TraceRouter
    db: TraceDB


_provider: Optional[Callable[[], Tenant]] = None


def set_tenant_provider(provider: Callable[[], Tenant]) -> None:
    """Called once at startup by api.py."""
    global _provider
    _provider = provider


def get_current_tenant() -> Tenant:
    if _provider is None:
        raise RuntimeError("MCP tenant provider not configured; call set_tenant_provider() at startup")
    return _provider()


# ---------------------------------------------------------------------------
# Shared helpers (sync — the blocking engine work; tools offload to a thread).
# ---------------------------------------------------------------------------
def _resolve_entities(
    tenant: Tenant, name: str, *, limit: int, min_score: float = 0.0
) -> list[dict]:
    """Name -> graph nodes. Exact label match first (canonical), then a semantic
    vector fallback so a near-miss name ("payments" for "PaymentService") resolves.

    ``min_score`` floors the semantic fallback: hits below it are dropped, so a
    nonsense name resolves to nothing instead of a spurious weak match. Exact
    matches always pass (score 1.0)."""
    exact = tenant.db.find_nodes_by_label(name)
    if exact:
        return [
            {"id": n["id"], "label": n["label"], "type": n["type"],
             "match": "exact", "score": 1.0}
            for n in exact[:limit]
        ]
    try:
        vec = tenant.router.embed_query(name)
        hits = tenant.db.vector_search(vec, k=limit)
    except Exception as exc:  # noqa: BLE001 — empty index, etc.
        logger.debug("vector resolve failed for %r (%s)", name, exc)
        return []
    return [
        {"id": h["id"], "label": h["label"], "type": h["type"],
         "match": "semantic", "score": round(float(h["similarity"]), 4)}
        for h in hits
        if float(h["similarity"]) >= min_score
    ]


def _citations_for(tenant: Tenant, entity_ids: list[str]) -> dict[str, list[dict]]:
    """Source documents (PRs / tickets / notes) that mention each entity, so the
    agent can ground and cite every claim instead of hallucinating."""
    if not entity_ids:
        return {}
    try:
        docs = tenant.db.documents_for_entities(entity_ids)
    except Exception as exc:  # noqa: BLE001
        logger.debug("citation lookup failed (%s)", exc)
        return {}
    out: dict[str, list[dict]] = {}
    for eid, dlist in docs.items():
        cites: list[dict] = []
        for d in dlist[: config.MCP_CITATIONS_PER_NODE]:
            content = (d.get("content") or "").strip()
            if not content:
                continue
            cites.append({
                "doc_id": d.get("doc_id"),
                "source": d.get("path"),
                "snippet": content[: config.MCP_SNIPPET_CHARS],
            })
        if cites:
            out[eid] = cites
    return out


def _trace_impact_impl(entity_name: str, max_hops: int) -> dict:
    tenant = get_current_tenant()
    name = (entity_name or "").strip()[: config.MAX_QUERY_CHARS]
    if not name:
        return {"query_entity": entity_name, "resolved": None, "impacted": [],
                "note": "Provide a non-empty entity name."}
    hops_cap = max(1, min(int(max_hops), config.MCP_MAX_HOPS))

    resolved = _resolve_entities(
        tenant, name, limit=1, min_score=config.MCP_RESOLVE_MIN_SIM
    )
    if not resolved:
        return {"query_entity": name, "resolved": None, "impacted": [],
                "note": "No entity in this graph confidently matched that name. "
                        "Call find_entity to list candidates."}
    seed = resolved[0]
    seed_id = seed["id"]

    # Multiplicative-confidence BFS: path strength = product of edge confidences,
    # so influence decays with distance (mirrors the router's graph arm). We also
    # record hop distance and the neighbor each node was reached through, so the
    # blast radius is explainable, not just a flat list.
    labels: dict[str, str] = {seed_id: seed["label"]}
    best: dict[str, dict] = {}
    frontier: dict[str, float] = {seed_id: 1.0}
    visited: set[str] = {seed_id}
    for depth in range(1, hops_cap + 1):
        if not frontier:
            break
        # Expand the seed generously (it's the entity the user asked about, often
        # a hub); keep normal hub-suppression on deeper hops so a *downstream*
        # super-connector can't blow up the traversal.
        degree_cap = config.MCP_SEED_MAX_DEGREE if depth == 1 else config.MAX_DEGREE
        expanded = tenant.db.expand_frontier(
            list(frontier), config.MCP_NEIGHBOR_K, degree_cap
        )
        nxt: dict[str, float] = {}
        for from_id, acc in frontier.items():
            for nb in expanded.get(from_id, []):
                to_id = nb["id"]
                labels.setdefault(to_id, nb["label"])
                score = acc * nb["confidence"]
                cur = best.get(to_id)
                if cur is None or score > cur["confidence"]:
                    best[to_id] = {
                        "id": to_id, "label": nb["label"], "type": nb["type"],
                        "confidence": round(score, 4), "hops": depth,
                        "via": labels.get(from_id, from_id),
                    }
                if to_id not in visited:
                    visited.add(to_id)
                    if score > nxt.get(to_id, 0.0):
                        nxt[to_id] = score
        frontier = nxt

    ranked = sorted(best.values(), key=lambda r: (-r["confidence"], r["hops"], r["id"]))
    ranked = ranked[: config.MCP_MAX_IMPACT]
    cites = _citations_for(tenant, [r["id"] for r in ranked])
    for r in ranked:
        r["citations"] = cites.get(r["id"], [])

    return {
        "query_entity": name,
        "resolved": seed,
        "hops_traversed": hops_cap,
        "blast_radius_count": len(ranked),
        "impacted": ranked,
    }


def _search_context_impl(query: str, top_k: int) -> dict:
    tenant = get_current_tenant()
    q = (query or "").strip()
    if not q:
        return {"query": query, "passages": [], "note": "Provide a non-empty query."}
    k = max(1, min(int(top_k), config.TOP_K_VECTOR * 2))
    resp = tenant.router.route(q, top_k=k)

    passages: list[dict] = []
    for node in resp.results:
        cites: list[dict] = []
        for d in node.documents[: config.MCP_CITATIONS_PER_NODE]:
            content = (d.get("content") or "").strip()
            if not content:
                continue
            cites.append({
                "doc_id": d.get("doc_id"),
                "source": d.get("path"),
                "snippet": content[: config.MCP_SNIPPET_CHARS],
            })
        passages.append({
            "entity": node.label or node.id,
            "type": node.type,
            "relevance": round(node.score_total, 4),
            "citations": cites,
        })

    intent = (resp.trace_log.get("intent") or {}).get("type")
    return {"query": resp.query, "intent": intent, "facts": resp.facts,
            "result_count": len(passages), "passages": passages}


def _write_refusal(token: str) -> dict | None:
    """None when the call may write. A missing or wrong token is refused."""
    expected = config.MCP_WRITE_TOKEN
    if not expected:
        return {"ok": False, "note": "Memory writes are disabled on this server."}
    # ponytail: the token rides in the tool call. Fine for one local agent; move it to
    # the transport's auth header before this server faces more than one client.
    if not hmac.compare_digest((token or "").encode(), expected.encode()):
        return {"ok": False, "note": "Wrong or missing write token."}
    return None


def _remember_impl(token: str, subject: str, relation: str, obj: str, replace: bool) -> dict:
    refused = _write_refusal(token)
    if refused:
        return refused
    tenant = get_current_tenant()
    try:
        stored = AgentMemory(tenant.db, tenant.router.embed_query).remember(
            subject, relation, obj, source="mcp", replace=replace)
    except ValueError as exc:
        return {"ok": False, "note": str(exc)}
    return {"ok": True, **stored}


def _forget_impl(token: str, subject: str, relation: str, obj: str) -> dict:
    refused = _write_refusal(token)
    if refused:
        return refused
    tenant = get_current_tenant()
    try:
        removed = AgentMemory(tenant.db, tenant.router.embed_query).forget(subject, relation, obj)
    except ValueError as exc:
        return {"ok": False, "note": str(exc)}
    return {"ok": True, "removed": removed}


def _find_entity_impl(name: str, limit: int) -> dict:
    tenant = get_current_tenant()
    n = (name or "").strip()
    if not n:
        return {"query": name, "candidates": [], "note": "Provide a non-empty name."}
    lim = max(1, min(int(limit), config.MCP_MAX_CANDIDATES))
    candidates = _resolve_entities(tenant, n, limit=lim)
    return {"query": n, "match_count": len(candidates), "candidates": candidates}


# ---------------------------------------------------------------------------
# The MCP server + tool surface. Docstrings ARE the prompt the agent reads to
# route intent, so they are written precisely — what each tool is for, when to
# prefer it over the others, and exactly what it returns.
# ---------------------------------------------------------------------------
if _MCP_AVAILABLE:
    mcp = FastMCP("TraceRAG", stateless_http=True)

    @mcp.tool()
    async def trace_impact(entity_name: str, max_hops: int = 3) -> dict:
        """Trace the blast radius of changing a code entity: given a service,
        module, class, PR, or ticket, return everything else in the codebase graph
        that is causally connected to it, ranked by how strongly.

        USE THIS WHEN the user asks what a change will affect or break — e.g.
        "I'm changing PaymentService, what else will this break?", "what depends
        on the auth module?", "what's downstream of this PR?", "impact of touching
        X". It walks the dependency graph outward from the entity across ALL
        repositories in the workspace, so it surfaces cross-repo and cross-project
        consequences (a backend change that breaks a frontend caller and reopens a
        linked ticket).

        PREFER THIS over search_context whenever the question is about
        consequences, dependencies, or impact — not "explain / what is". If the
        entity name is ambiguous, call find_entity first to pick the exact one.

        Args:
            entity_name: The entity to start from (e.g. "PaymentService", "auth",
                a PR title). Matched exactly first, then by semantic similarity if
                there is no exact match.
            max_hops: How many dependency hops to follow outward (1-4, default 3).
                Higher reaches farther but returns weaker, more indirect links.

        Returns a JSON object:
            resolved: the entity the trace actually started from (id, label, type,
                match — "exact" or "semantic"). Null if nothing matched.
            impacted: affected entities, strongest first, each with label, type,
                confidence (0-1 path strength, decays per hop), hops (distance),
                via (the neighbor it was reached through), and citations (source
                PRs / tickets / docs with snippets). Cite these; do not invent.
            blast_radius_count: how many entities were reached.
        """
        return await asyncio.to_thread(_trace_impact_impl, entity_name, max_hops)

    @mcp.tool()
    async def search_context(query: str, top_k: int = 8) -> dict:
        """Answer a natural-language question about the codebase using hybrid
        retrieval (semantic vector search fused with graph context), returning
        ranked passages with their source citations.

        USE THIS WHEN the user wants to understand or explain something rather than
        trace impact — e.g. "why was retry logic added to the consumer?", "how does
        the billing flow work?", "what is PaymentService responsible for?",
        "summarize the recent auth changes". This is the general "ask the codebase"
        tool.

        PREFER trace_impact instead when the question is specifically about what a
        change will break or what depends on an entity.

        Args:
            query: The natural-language question.
            top_k: Maximum passages to return (default 8).

        Returns a JSON object:
            intent: how the query was routed ("relational" vs "semantic").
            passages: ranked list, each with entity, type, relevance (0-1), and
                citations (source PRs / tickets / docs with snippets). Ground every
                claim in these citations and cite the source; do not state facts
                that are not present in them.
            result_count: number of passages returned.
        """
        return await asyncio.to_thread(_search_context_impl, query, top_k)

    @mcp.tool()
    async def find_entity(name: str, limit: int = 5) -> dict:
        """Resolve a name to the specific entities that exist in the codebase graph
        — a lightweight disambiguation lookup. Returns candidate entities (exact
        matches first, then closest semantic matches) so you can pick the right one
        before calling trace_impact.

        USE THIS WHEN a name is ambiguous or you are unsure it exists — e.g. the
        user says "PaymentService" but there may be one in two different repos, or
        you want to confirm the exact label before tracing impact. This does NOT
        traverse the graph or answer questions; it only identifies entities.

        Args:
            name: The entity name or fragment to look up.
            limit: Maximum candidates to return (default 5).

        Returns a JSON object:
            candidates: matches, each with id, label, type, match ("exact" or
                "semantic"), and score (1.0 for exact, cosine similarity for
                semantic). Use a candidate's label as entity_name for trace_impact.
            match_count: number of candidates found.
        """
        return await asyncio.to_thread(_find_entity_impl, name, limit)

    if config.MCP_WRITE_TOKEN:

        @mcp.tool()
        async def remember(token: str, subject: str, relation: str, obj: str,
                           replace: bool = False) -> dict:
            """Store a fact you learned, as subject -RELATION-> object, so later
            questions can use it. Example: subject "checkout-service", relation
            "OWNED_BY", obj "payments team".

            USE THIS WHEN the user tells you something about the codebase that the
            repository itself doesn't record: who owns what, a decision, a known
            workaround. Don't store what search_context already returns.

            Set replace=True when the fact supersedes an older one with the same
            subject and relation (ownership moved, a decision changed). The old fact
            stops being returned but is kept as history.

            Remembered facts come back labelled "(remembered, source: mcp)", and they
            never override facts read from GitHub.

            Args:
                token: The write token this server was configured with.
                subject, obj: Entity names. An existing entity is matched by exact
                    name; a new name becomes a new node.
                relation: A short name such as OWNED_BY or DECIDED.
                replace: End this subject's other facts with the same relation.

            Returns ok, the stored ids, and how many facts were replaced.
            """
            return await asyncio.to_thread(_remember_impl, token, subject, relation, obj, replace)

        @mcp.tool()
        async def forget(token: str, subject: str, relation: str, obj: str) -> dict:
            """Delete a fact that remember stored, history included. Use it when a
            remembered fact was wrong rather than out of date (for out of date, use
            remember with replace=True). Facts read from GitHub can't be forgotten.

            Returns ok and how many facts were removed.
            """
            return await asyncio.to_thread(_forget_impl, token, subject, relation, obj)

else:  # pragma: no cover — SDK absent
    mcp = None


# ---------------------------------------------------------------------------
# ASGI wiring helpers used by api.py. All are safe no-ops when the SDK is absent.
# ---------------------------------------------------------------------------
_asgi_app = None


def is_available() -> bool:
    return _MCP_AVAILABLE


def build_app():
    """The Streamable-HTTP ASGI app to mount (built once). None if SDK absent."""
    global _asgi_app
    if not _MCP_AVAILABLE:
        return None
    if _asgi_app is None:
        _asgi_app = mcp.streamable_http_app()
    return _asgi_app


@asynccontextmanager
async def session_lifespan():
    """Run the MCP session manager for the app's lifetime.

    FastMCP's Streamable-HTTP transport needs its session manager task group
    running; a mounted sub-app's lifespan isn't invoked by the parent, so the
    parent app must drive it. api.py wraps its `yield` in this. No-op when the SDK
    is absent or the app was never built.
    """
    if _MCP_AVAILABLE and build_app() is not None:
        async with mcp.session_manager.run():
            yield
    else:
        yield
