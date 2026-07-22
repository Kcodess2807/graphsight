"""FastAPI backend for the dashboard."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

from tracerag import config
from tracerag.db import TraceDB
from tracerag.router import TraceRouter, shutdown_embed_executor
from tracerag.integrations.langchain import format_page_content

from auth import get_current_user, get_current_tenant_org
from cache import LRUCache
from database import init_db
from ratelimit import limiter, LLM_RATE_LIMIT
from routers import history, onboarding, github_oauth, webhooks
from registry import REGISTRY, default_tenant_loader, set_model_source
from middleware.routing import TenantRoutingMiddleware
import mcp_server

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tracerag.api")

# Error tracking + performance monitoring. No-op when SENTRY_DSN is unset, so
# dev runs are unaffected. Initialized before the app is created so Sentry's
# auto-enabled FastAPI/Starlette/asyncio/threading integrations hook in — the
# asyncio + threading ones are what capture errors raised inside our async
# routes and the embed ThreadPoolExecutor (they re-raise via future.result()).
if config.SENTRY_ENABLED:
    import sentry_sdk

    sentry_sdk.init(
        dsn=config.SENTRY_DSN,
        environment=config.SENTRY_ENVIRONMENT,
        traces_sample_rate=config.SENTRY_TRACES_SAMPLE_RATE,
        send_default_pii=False,  # don't ship request bodies / auth headers to Sentry
    )
    logger.info(
        "Sentry enabled (env=%s, traces_sample_rate=%.2f)",
        config.SENTRY_ENVIRONMENT, config.SENTRY_TRACES_SAMPLE_RATE,
    )

_state: dict = {}


# --- Tenant graph resolution (single path for both single- and multi-tenant) ---
def _mcp_tenant_provider(org_id: str) -> "mcp_server.Tenant":
    """Resolve an org_id to its MCP tenant (router+db) via the shared registry,
    falling back to the warm local graph in single-tenant mode."""
    lg = REGISTRY.get_tenant(org_id)
    if lg is not None and lg.router is not None and lg.db is not None:
        return mcp_server.Tenant(router=lg.router, db=lg.db,
                                 graph_id=lg.artifact_id or org_id)
    if not config.MULTI_TENANCY_ENABLED:
        return mcp_server.Tenant(
            router=_state["router"], db=_state["db"],
            graph_id=(Path(_state.get("db_path", "")).name or org_id),
        )
    raise RuntimeError(f"tenant graph not loaded on this pod: {org_id}")


def _resolve_tenant(org_id: str):
    """(router, db) for an org via the registry; warm local graph in dev; 503 if a
    multi-tenant graph isn't loaded on this pod."""
    lg = REGISTRY.get_tenant(org_id)
    if lg is not None and lg.router is not None and lg.db is not None:
        return lg.router, lg.db
    if not config.MULTI_TENANCY_ENABLED:
        return _state["router"], _state["db"]
    raise HTTPException(status_code=503,
                        detail=f"Tenant graph not loaded on this pod: {org_id}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: open the DB + warm models. Shutdown: drain pools, flush to disk."""
    # ---- startup --------------------------------------------------------------
    db = TraceDB(config.DB_PATH)
    db.init_schema()
    _state["db"] = db
    _state["db_path"] = str(config.DB_PATH)
    _state["router"] = TraceRouter(db)

    # Cold-boot warmup: pull model weights into RAM and spin up the embed-executor
    # threads + spaCy pipeline, so the first real UI query skips the cold-start
    # latency spike. Runs off the event loop and never blocks boot on failure.
    try:
        await asyncio.to_thread(_state["router"].warm)
        logger.info("Warmup complete (embedder + executor threads + spaCy primed).")
    except Exception as exc:  # noqa: BLE001 — warmup is best-effort
        logger.warning("Router warmup skipped (%s).", exc)

    # history is optional; api still boots without it
    try:
        init_db()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Postgres history disabled (%s).", exc)

    # In multi-tenant mode, provision the control-plane + graph-store schemas on
    # boot so a fresh stack is self-initializing (single-tenant/dev skips this).
    if config.MULTI_TENANCY_ENABLED:
        try:
            from models.control_plane import init_control_plane
            from models.graph_store import init_graph_store

            init_control_plane()
            init_graph_store()
            logger.info("Control-plane + graph-store schemas ready (multi-tenant).")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Multi-tenant schema init skipped (%s).", exc)

    # Tenant graph resolution goes through the shared registry. Bind the warm
    # local graph as the DEFAULT tenant so single-tenant serves through the exact
    # same path (no second load), and register the handle loader so the pod agent
    # can open real per-tenant graphs later (sharing the warm models). The MCP
    # provider now resolves per org_id — the same function serves both modes.
    REGISTRY.set_handle_loader(default_tenant_loader)
    set_model_source(_state["router"])   # tenants share this warm embedder/spaCy
    REGISTRY.bind(
        config.DEFAULT_TENANT_ORG_ID,
        db=_state["db"], router=_state["router"],
        artifact_id="local-default", version=0, path=_state.get("db_path"),
    )
    mcp_server.set_tenant_provider(_mcp_tenant_provider)

    # Optional: run the pod agent (the multi-tenant REALITY loop) on this web pod.
    # Off by default (POD_AGENT_ENABLED != "1"), so the single-tenant demo and the
    # HF deploy are completely unaffected; it needs the control-plane DB configured.
    if os.getenv("POD_AGENT_ENABLED") == "1":
        import lifecycle
        import pod_agent

        # Boot sync: register this pod in the fleet + re-hydrate any tenants it was
        # already assigned (so a rescheduled/crashed pod serves immediately, before
        # any user intent check). Off the event loop; never blocks boot on failure.
        try:
            hydrated = await asyncio.to_thread(lifecycle.boot_pod, config.POD_ID)
            logger.info("Pod boot: registered + hydrated %d assigned tenant(s).",
                        len(hydrated))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Pod boot sync skipped (%s).", exc)

        _state["pod_agent_stop"] = asyncio.Event()
        _state["pod_agent_task"] = asyncio.create_task(
            pod_agent.run_pod_agent(_state["pod_agent_stop"])
        )
        logger.info("Pod agent enabled (pod_id=%s).", pod_agent.POD_ID)

    logger.info("TraceRAG STUDIO API ready (db=%s)", config.DB_PATH)
    try:
        # session_lifespan drives FastMCP's Streamable-HTTP session manager for
        # the mounted /mcp sub-app (a no-op when the MCP SDK isn't installed).
        async with mcp_server.session_lifespan():
            yield
    finally:
        # Stop the pod agent first (if running): signal + await the task.
        _agent_task = _state.get("pod_agent_task")
        if _agent_task is not None:
            _state["pod_agent_stop"].set()
            try:
                await _agent_task
            except Exception as exc:  # noqa: BLE001
                logger.warning("Pod agent shutdown failed: %s", exc)
        # ---- graceful shutdown ------------------------------------------------
        # Close BOTH the original and the currently-active DB: a graph hot-swap
        # replaces _state["db"] with a new TraceDB, so the active one would
        # otherwise leak its pooled connections. close() drains every leased
        # connection and lets LadybugDB flush its WAL to disk (idempotent, so
        # closing an already-swapped-out handle is a safe no-op).
        for handle in {db, _state.get("db")}:  # set dedupes when no swap happened
            if handle is None:
                continue
            try:
                handle.close()
            except Exception as exc:  # noqa: BLE001
                logger.warning("DB close failed during shutdown: %s", exc)
        # Join the embed executor's worker threads (let in-flight encodes finish).
        try:
            shutdown_embed_executor(wait=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Embed executor shutdown failed: %s", exc)
        logger.info("TraceRAG shutdown complete (pools drained, flushed to disk).")


app = FastAPI(title="TraceRAG STUDIO API", version="0.1.0", lifespan=lifespan)

# Rate limiting: slowapi reads the limiter off app.state, and the handler turns
# the library's RateLimitExceeded into a clean HTTP 429 (+ Retry-After header).
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(history.router)
app.include_router(onboarding.router)   # admin tenant provisioning (X-Admin-Secret)
app.include_router(github_oauth.router) # GitHub OAuth connect (encrypts the token)
app.include_router(webhooks.router)     # real-time GitHub webhook -> debounce

# Gateway routing simulation: gate tenant-scoped routes on this pod's
# PodAssignment (no-op unless MULTI_TENANCY_ENABLED). Added BEFORE CORS so CORS
# stays the outermost layer and its headers apply even to 421/409/503 rejections.
app.add_middleware(TenantRoutingMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,  # "*" by default; lock to the frontend in prod
    allow_methods=["*"],
    allow_headers=["*"],
)

# Agent-facing MCP surface (Cursor / Claude Desktop) mounted as a Streamable-HTTP
# sub-app. Semantic tools only — no raw Cypher. The parent app's CORS middleware
# wraps it; the session manager is driven from the lifespan above. Skipped cleanly
# when disabled or the SDK is absent, so the core API is never affected.
if config.MCP_ENABLED and mcp_server.is_available():
    app.mount(config.MCP_MOUNT_PATH, mcp_server.build_app())
    logger.info("MCP server mounted at %s (tools: trace_impact, search_context, "
                "find_entity)", config.MCP_MOUNT_PATH)
elif config.MCP_ENABLED:
    logger.info("MCP enabled but SDK not installed; /mcp surface unavailable.")


class TraceRequest(BaseModel):
    query: str
    top_k: int | None = None
    session_id: str | None = None  # set -> persist this execution


class SubgraphRequest(BaseModel):
    node_ids: list[str]


@app.post("/api/trace")
async def trace(
    req: TraceRequest,
    user_id: str = Depends(get_current_user),           # who (Clerk user)
    org_id: str = Depends(get_current_tenant_org),      # which tenant graph
) -> dict:
    """Run the router and return the full trace for visualization."""
    router, _db = _resolve_tenant(org_id)
    # aroute offloads the blocking hybrid retrieval (DB pool + embed pool) off
    # the event loop, so concurrent requests no longer serialize on one thread.
    response = await router.aroute(req.query, top_k=req.top_k or config.TOP_K_VECTOR)
    payload = asdict(response)
    # rendered context the generation model would receive
    for node, result in zip(response.results, payload["results"]):
        result["page_content"] = format_page_content(node)
    payload["context"] = router.build_context(response.results)
    if req.session_id:
        # Ownership check (write-side IDOR): only persist into a session that
        # belongs to the authenticated user. Unknown session → 404; someone
        # else's session → 403. A query with no session_id stays anonymous.
        # Postgres calls are blocking → run them off the loop too.
        owner = await asyncio.to_thread(history.session_owner, req.session_id)
        if owner is None:
            raise HTTPException(status_code=404, detail="session not found")
        if owner != user_id:
            raise HTTPException(status_code=403, detail="not your session")
        payload["trace_id"] = await asyncio.to_thread(
            history.persist_trace,
            session_id=req.session_id,
            query=req.query,
            execution_plan=payload["trace_log"],
            graph_payload=payload["results"],
        )
    return payload


@app.post("/api/subgraph")
async def subgraph(
    req: SubgraphRequest,
    org_id: str = Depends(get_current_tenant_org),
) -> dict:
    """Requested nodes plus their 1-hop neighbors and edges."""
    _router, db = _resolve_tenant(org_id)
    # blocking DB read -> offload so the loop stays free under concurrency
    return await asyncio.to_thread(db.subgraph, req.node_ids)


class SummarizeRequest(BaseModel):
    key: str           # cache key (doc id / node id)
    text: str


# bounded so a long-running server can't leak memory; LRU evicts cold snippets
_SUMMARY_CACHE: LRUCache[str, str] = LRUCache(capacity=512)


@app.post("/api/summarize")
@limiter.limit(LLM_RATE_LIMIT)  # per-user cap; needs the `request` param below
def summarize(
    request: Request,  # required by slowapi to read the rate-limit key
    req: SummarizeRequest,
    _user: str = Depends(get_current_user),  # require a valid token (LLM = billed)
) -> dict:
    """One-sentence LLM summary of a node's snippet, cached by key."""
    key = req.key or req.text[:64]
    cached = _SUMMARY_CACHE.get(key)
    if cached is not None:
        return {"summary": cached, "cached": True}
    text = (req.text or "").strip()
    if not text:
        return {"summary": "", "cached": False}
    try:
        client = _state.get("llm")
        if client is None:
            from tracerag.llm import make_client

            client = make_client()
            _state["llm"] = client
        resp = client.chat.completions.create(
            model=config.OPENROUTER_MODEL,
            messages=[{
                "role": "user",
                "content": (
                    "Summarize this engineering note in one concise sentence "
                    "(max 25 words): what changed and why. Reply with only the "
                    "sentence.\n\n" + text
                ),
            }],
            temperature=0,
        )
        summary = (resp.choices[0].message.content or "").strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("summarize failed for %s: %s", key, exc)
        return {"summary": "", "cached": False, "error": str(exc)}
    _SUMMARY_CACHE.set(key, summary)
    return {"summary": summary, "cached": False}


# swap the active .lbug without restarting; router models stay warm
def _graphs_dir() -> Path:
    return config.PROJECT_ROOT / "graphs"


def _graph_label(path: Path) -> str:
    stem = path.stem
    if path.resolve() == config.DB_PATH.resolve():
        return f"{stem} (default)"
    return stem.replace("__", "/")  # pallets__flask -> pallets/flask


def discover_graphs() -> list[Path]:
    """Selectable .lbug files: the configured default plus graphs/*."""
    paths: list[Path] = []
    if config.DB_PATH.exists():
        paths.append(config.DB_PATH)
    gdir = _graphs_dir()
    if gdir.exists():
        paths.extend(sorted(gdir.glob("*.lbug")))
    seen: set[Path] = set()
    out: list[Path] = []
    for p in paths:
        rp = p.resolve()
        if rp not in seen:
            seen.add(rp)
            out.append(p)
    return out


class SwitchGraphRequest(BaseModel):
    id: str  # the graph's file name


@app.get("/api/graphs")
def list_graphs() -> dict:
    active = _state.get("db_path")
    active_rp = Path(active).resolve() if active else None
    graphs = [
        {
            "id": p.name,
            "label": _graph_label(p),
            "active": active_rp is not None and p.resolve() == active_rp,
        }
        for p in discover_graphs()
    ]
    return {"graphs": graphs, "active": Path(active).name if active else None}


@app.post("/api/graphs/switch")
def switch_graph(req: SwitchGraphRequest) -> dict:
    """Hot-swap the active graph; id must be one of the discovered files."""
    target = next((p for p in discover_graphs() if p.name == req.id), None)
    if target is None:
        raise HTTPException(status_code=404, detail=f"unknown graph: {req.id}")

    old = _state.get("db")
    new_db = TraceDB(target)
    new_db.init_schema()
    # re-point router at the new connection, keep warm models
    _state["db"] = new_db
    _state["db_path"] = str(target)
    _state["router"].db = new_db
    # keep the default-tenant registry entry in sync so tenant resolution (and
    # the MCP tools) follow the hot-swap too.
    REGISTRY.bind(config.DEFAULT_TENANT_ORG_ID, db=new_db, router=_state["router"],
                  artifact_id="local-default", version=0, path=str(target))
    _SUMMARY_CACHE.clear()  # snippets differ per graph
    if old is not None and old is not new_db:
        try:
            old.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("closing previous graph failed: %s", exc)

    logger.info("Switched active graph -> %s", target)
    return {
        "active": target.name,
        "label": _graph_label(target),
        "nodes": new_db.count_nodes(),
    }


# per-entity-type question templates
_SUGGESTION_TEMPLATES: dict[str, str] = {
    "Person": "What did {label} work on?",
    "Team": "What does {label} own?",
    "Service": "What depends on {label}?",
    "Library": "What changed in {label}?",
    "Tool": "What is {label} used for?",
    "PR": "What is related to {label}?",
    "Ticket": "What is linked to {label}?",
}
_SUGGESTION_DEFAULT = "What is related to {label}?"


@app.get("/api/suggestions")
def suggestions(
    limit: int = 5,
    org_id: str = Depends(get_current_tenant_org),
) -> dict:
    """Example questions built from the active graph's hub entities."""
    _router, db = _resolve_tenant(org_id)
    try:
        hubs = db.top_entities(limit=limit * 4)  # over-fetch, then diversify
    except Exception as exc:  # noqa: BLE001
        logger.warning("top_entities failed: %s", exc)
        return {"suggestions": []}

    out: list[dict] = []
    seen_types: dict[str, int] = {}
    # one question per type, in degree order
    for ent in hubs:
        etype = ent.get("type") or ""
        label = (ent.get("label") or "").strip()
        if not label or seen_types.get(etype, 0) >= 1:
            continue
        tmpl = _SUGGESTION_TEMPLATES.get(etype, _SUGGESTION_DEFAULT)
        out.append({"query": tmpl.format(label=label), "entity": label, "type": etype})
        seen_types[etype] = seen_types.get(etype, 0) + 1
        if len(out) >= limit:
            break
    # backfill by degree if we still have room
    if len(out) < limit:
        used = {s["query"] for s in out}
        for ent in hubs:
            label = (ent.get("label") or "").strip()
            if not label:
                continue
            tmpl = _SUGGESTION_TEMPLATES.get(ent.get("type") or "", _SUGGESTION_DEFAULT)
            q = tmpl.format(label=label)
            if q in used:
                continue
            out.append({"query": q, "entity": label, "type": ent.get("type") or ""})
            used.add(q)
            if len(out) >= limit:
                break
    return {"suggestions": out}


class AnswerRequest(BaseModel):
    query: str
    context: str


# bounded LRU shared by the blocking and streaming answer endpoints below
_ANSWER_CACHE: LRUCache[str, str] = LRUCache(capacity=512)


def _answer_key(query: str, context: str) -> str:
    return f"{query}\n#{hash(context)}"


def _answer_prompt(query: str, context: str) -> str:
    """Grounded-answer prompt shared by the blocking and streaming endpoints."""
    return (
        "You are answering a teammate's question about an engineering "
        "knowledge graph. Use ONLY the context below. Answer in 2-3 "
        "plain sentences a non-expert can follow, naming the specific "
        "PRs / people / components involved. If the context does not "
        "contain the answer, say so plainly rather than guessing.\n\n"
        f"Question: {query}\n\nContext:\n{context}"
    )


def _answer_client():
    """Lazily build and cache the OpenRouter client."""
    client = _state.get("llm")
    if client is None:
        from tracerag.llm import make_client

        client = make_client()
        _state["llm"] = client
    return client


@app.post("/api/answer")
@limiter.limit(LLM_RATE_LIMIT)  # per-user cap; needs the `request` param below
def answer(
    request: Request,  # required by slowapi to read the rate-limit key
    req: AnswerRequest,
    _user: str = Depends(get_current_user),  # require a valid token (LLM = billed)
) -> dict:
    """Plain-language answer grounded in the retrieved context, cached per (query, context)."""
    key = _answer_key(req.query, req.context)
    cached = _ANSWER_CACHE.get(key)
    if cached is not None:
        return {"answer": cached, "cached": True}
    context = (req.context or "").strip()
    if not context:
        return {"answer": "No supporting context was retrieved for this query.",
                "cached": False}
    try:
        resp = _answer_client().chat.completions.create(
            model=config.OPENROUTER_MODEL,
            messages=[{"role": "user", "content": _answer_prompt(req.query, context)}],
            temperature=0,
        )
        text = (resp.choices[0].message.content or "").strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("answer failed: %s", exc)
        return {"answer": "", "cached": False, "error": str(exc)}
    _ANSWER_CACHE.set(key, text)
    return {"answer": text, "cached": False}


@app.post("/api/answer/stream")
@limiter.limit(LLM_RATE_LIMIT)  # same per-user cap — the streaming twin hits the
                               # same billing API, so it must be capped too
def answer_stream(
    request: Request,  # required by slowapi to read the rate-limit key
    req: AnswerRequest,
    _user: str = Depends(get_current_user),  # require a valid token (LLM = billed)
) -> StreamingResponse:
    """Same answer as /api/answer, streamed token-by-token as plain UTF-8 chunks."""

    def gen():
        key = _answer_key(req.query, req.context)
        cached = _ANSWER_CACHE.get(key)
        if cached is not None:
            yield cached
            return
        context = (req.context or "").strip()
        if not context:
            yield "No supporting context was retrieved for this query."
            return
        parts: list[str] = []
        try:
            stream = _answer_client().chat.completions.create(
                model=config.OPENROUTER_MODEL,
                messages=[{"role": "user", "content": _answer_prompt(req.query, context)}],
                temperature=0,
                stream=True,
            )
            for chunk in stream:
                # guard every level; providers differ
                delta = ""
                try:
                    delta = chunk.choices[0].delta.content or ""
                except (AttributeError, IndexError):
                    delta = ""
                if delta:
                    parts.append(delta)
                    yield delta
        except Exception as exc:  # noqa: BLE001
            logger.warning("answer stream failed: %s", exc)
            if not parts:
                yield "Sorry — the answer could not be generated right now."
            return
        full = "".join(parts).strip()
        if full:
            _ANSWER_CACHE.set(key, full)

    # no-store + disable proxy buffering so chunks flush immediately
    return StreamingResponse(
        gen(),
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@app.get("/api/health")
def health() -> dict:
    db: TraceDB = _state["db"]
    return {"status": "ok", "nodes": db.count_nodes()}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host="127.0.0.1", port=8000, reload=True)
