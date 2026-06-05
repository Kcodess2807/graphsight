"""FastAPI backend for the TraceRAG STUDIO dashboard.

    uvicorn api:app --reload

Endpoints:
    POST /api/trace      {"query": str}            -> RouterResponse (results + trace_log)
    POST /api/subgraph   {"node_ids": [str]}       -> {nodes, edges} (1-hop bounded)
    GET  /api/health                                -> {status, nodes}
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from tracerag import config
from tracerag.db import TraceDB
from tracerag.router import TraceRouter
from tracerag.integrations.langchain import format_page_content

from database import init_db
from routers import history

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tracerag.api")

# Singletons populated on startup (one DB connection + router for the process).
_state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = TraceDB(config.DB_PATH)
    db.init_schema()
    _state["db"] = db
    _state["db_path"] = str(config.DB_PATH)
    _state["router"] = TraceRouter(db)
    # Pre-load embedder + spaCy now so the first real query is ~70ms, not ~5s
    # (one-time model loads otherwise land inside the first request's seeds phase).
    try:
        _state["router"].warm()
    except Exception as exc:  # noqa: BLE001 — never let warmup block boot
        logger.warning("Router warmup skipped (%s).", exc)
    # Postgres history is optional: if APP_DATABASE_URL is unset or unreachable,
    # the API still boots for pure retrieval — only history endpoints fail.
    try:
        init_db()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Postgres history disabled (%s).", exc)
    logger.info("TraceRAG STUDIO API ready (db=%s)", config.DB_PATH)
    try:
        yield
    finally:
        db.close()


app = FastAPI(title="TraceRAG STUDIO API", version="0.1.0", lifespan=lifespan)
app.include_router(history.router)

# Allow the React dev server to call us.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class TraceRequest(BaseModel):
    query: str
    top_k: int | None = None
    session_id: str | None = None  # set -> persist this execution to Postgres


class SubgraphRequest(BaseModel):
    node_ids: list[str]


@app.post("/api/trace")
def trace(req: TraceRequest) -> dict:
    """Run the hybrid router and return the full trace for visualization."""
    router: TraceRouter = _state["router"]
    response = router.route(req.query, top_k=req.top_k or config.TOP_K_VECTOR)
    payload = asdict(response)
    # Attach the rendered LLM-facing context (entity line + chunk snippets) so
    # the UI can show exactly what the generation model would receive.
    for node, result in zip(response.results, payload["results"]):
        result["page_content"] = format_page_content(node)
    # Assembled grounded context (cheap, no LLM) — the frontend feeds this to
    # /api/answer to generate the plain-language answer shown above the graph.
    payload["context"] = router.build_context(response.results)
    # Persist to Postgres history when a session is attached (best-effort).
    if req.session_id:
        payload["trace_id"] = history.persist_trace(
            session_id=req.session_id,
            query=req.query,
            execution_plan=payload["trace_log"],
            graph_payload=payload["results"],
        )
    return payload


@app.post("/api/subgraph")
def subgraph(req: SubgraphRequest) -> dict:
    """Bounded subgraph: requested nodes + 1-hop neighbors + their edges."""
    db: TraceDB = _state["db"]
    return db.subgraph(req.node_ids)


class SummarizeRequest(BaseModel):
    key: str           # cache key (doc id / node id) — dedupes repeat hovers
    text: str


# Process-lifetime cache: each snippet is summarized by the LLM exactly once.
_SUMMARY_CACHE: dict[str, str] = {}


@app.post("/api/summarize")
def summarize(req: SummarizeRequest) -> dict:
    """One-sentence LLM summary of a node's source snippet, cached by key.

    Called lazily on hover, so it never adds latency to /api/trace. The first
    hover per node pays one LLM round-trip; subsequent hovers are free.
    """
    key = req.key or req.text[:64]
    if key in _SUMMARY_CACHE:
        return {"summary": _SUMMARY_CACHE[key], "cached": True}
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
    except Exception as exc:  # noqa: BLE001 — summary is best-effort
        logger.warning("summarize failed for %s: %s", key, exc)
        return {"summary": "", "cached": False, "error": str(exc)}
    _SUMMARY_CACHE[key] = summary
    return {"summary": summary, "cached": False}


# --------------------------------------------------------------------------- #
# Graph switching — flip the active .lbug without restarting the server.
# Only the DB connection is swapped; the router's loaded models stay warm.
# --------------------------------------------------------------------------- #
def _graphs_dir() -> Path:
    return config.PROJECT_ROOT / "graphs"


def _graph_label(path: Path) -> str:
    stem = path.stem
    if path.resolve() == config.DB_PATH.resolve():
        return f"{stem} (default)"
    return stem.replace("__", "/")  # pallets__flask -> pallets/flask


def discover_graphs() -> list[Path]:
    """Whitelist of selectable .lbug files: the configured default + graphs/*."""
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
    id: str  # the graph's file name, e.g. "pallets__flask.lbug"


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
    """Hot-swap the active graph. The id must be one of the discovered files
    (whitelist — no arbitrary filesystem paths)."""
    target = next((p for p in discover_graphs() if p.name == req.id), None)
    if target is None:
        raise HTTPException(status_code=404, detail=f"unknown graph: {req.id}")

    old = _state.get("db")
    new_db = TraceDB(target)
    new_db.init_schema()
    # Re-point the router at the new connection; keep its warm models.
    _state["db"] = new_db
    _state["db_path"] = str(target)
    _state["router"].db = new_db
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


# Per-entity-type question templates. Keeping these server-side means the
# suggestions stay meaningful as new entity types are added to config, and the
# frontend just renders whatever questions it gets back.
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
def suggestions(limit: int = 5) -> dict:
    """Graph-aware example questions, built from the active graph's hub entities.

    Fixes the "ask the wrong thing" problem: instead of generic ShopFlow demo
    prompts, the UI offers questions that THIS graph can actually answer. We pull
    the most-connected entities and template one question each, diversifying by
    type so the list isn't five near-identical Person questions.
    """
    db: TraceDB = _state["db"]
    try:
        hubs = db.top_entities(limit=limit * 4)  # over-fetch, then diversify
    except Exception as exc:  # noqa: BLE001 — suggestions are best-effort
        logger.warning("top_entities failed: %s", exc)
        return {"suggestions": []}

    out: list[dict] = []
    seen_types: dict[str, int] = {}
    # First pass: at most one question per type, in degree order, for variety.
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
    # Second pass: if we still have room (few distinct types), backfill by degree.
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


_ANSWER_CACHE: dict[str, str] = {}


@app.post("/api/answer")
def answer(req: AnswerRequest) -> dict:
    """Plain-language answer to the query, grounded ONLY in the retrieved
    context. Called lazily after the graph renders, so it never blocks the
    trace. Cached per (query, context)."""
    key = f"{req.query}\n#{hash(req.context)}"
    if key in _ANSWER_CACHE:
        return {"answer": _ANSWER_CACHE[key], "cached": True}
    context = (req.context or "").strip()
    if not context:
        return {"answer": "No supporting context was retrieved for this query.",
                "cached": False}
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
                    "You are answering a teammate's question about an engineering "
                    "knowledge graph. Use ONLY the context below. Answer in 2-3 "
                    "plain sentences a non-expert can follow, naming the specific "
                    "PRs / people / components involved. If the context does not "
                    "contain the answer, say so plainly rather than guessing.\n\n"
                    f"Question: {req.query}\n\nContext:\n{context}"
                ),
            }],
            temperature=0,
        )
        text = (resp.choices[0].message.content or "").strip()
    except Exception as exc:  # noqa: BLE001 — answer is best-effort
        logger.warning("answer failed: %s", exc)
        return {"answer": "", "cached": False, "error": str(exc)}
    _ANSWER_CACHE[key] = text
    return {"answer": text, "cached": False}


@app.get("/api/health")
def health() -> dict:
    db: TraceDB = _state["db"]
    return {"status": "ok", "nodes": db.count_nodes()}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host="127.0.0.1", port=8000, reload=True)
