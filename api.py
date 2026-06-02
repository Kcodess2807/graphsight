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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from tracerag import config
from tracerag.db import TraceDB
from tracerag.router import TraceRouter
from tracerag.integrations.langchain import format_page_content

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tracerag.api")

# Singletons populated on startup (one DB connection + router for the process).
_state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = TraceDB(config.DB_PATH)
    db.init_schema()
    _state["db"] = db
    _state["router"] = TraceRouter(db)
    logger.info("TraceRAG STUDIO API ready (db=%s)", config.DB_PATH)
    try:
        yield
    finally:
        db.close()


app = FastAPI(title="TraceRAG STUDIO API", version="0.1.0", lifespan=lifespan)

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
    return payload


@app.post("/api/subgraph")
def subgraph(req: SubgraphRequest) -> dict:
    """Bounded subgraph: requested nodes + 1-hop neighbors + their edges."""
    db: TraceDB = _state["db"]
    return db.subgraph(req.node_ids)


@app.get("/api/health")
def health() -> dict:
    db: TraceDB = _state["db"]
    return {"status": "ok", "nodes": db.count_nodes()}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host="127.0.0.1", port=8000, reload=True)
