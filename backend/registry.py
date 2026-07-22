"""In-memory tenant graph registry — the REALITY side of the state machine, on
the serving pod. Maps org_id -> the graph handle that pod currently serves.

Two ways an entry lands here:
  * bind()  — attach an already-open handle (single-tenant startup binds the warm
              _state graph; also used by tests).
  * swap()  — the pod agent points an org at a freshly downloaded artifact. If a
              handle loader is registered, swap opens the real graph; otherwise it
              records the path only (enough for the pure-orchestration tests).

The swap is a single locked dict assignment, so a concurrent reader sees either
the old graph or the new one, never a half-open handle — the same pointer-flip
guarantee as the single-tenant hot-swap in api.py.

Decoupling: this module never imports the RAG engine. Handles (TraceDB /
TraceRouter) are opaque here; api.py injects a loader that knows how to open one
(sharing warm models), so pod_agent can stay torch-free.
"""

import logging
import threading
from dataclasses import dataclass
from typing import Any, Callable, Optional

logger = logging.getLogger("tracerag.registry")

# loader(org_id, file_path) -> (router, db): opens a graph from a local artifact
# path. None => path-only records (the pure-orchestration tests).
HandleLoader = Callable[[str, str], "tuple[Any, Any]"]

# The warm model source: a TraceRouter whose embedder/spaCy are already loaded.
# default_tenant_loader copies these references into every tenant router so a new
# tenant reuses the single in-RAM MiniLM + spaCy instead of loading its own ~2 GB.
_model_source: Any = None


def set_model_source(router: Any) -> None:
    """Register the warm router whose loaded models tenant graphs should share."""
    global _model_source
    _model_source = router


def default_tenant_loader(org_id: str, file_path: str) -> "tuple[Any, Any]":
    """Open a real graph from an artifact file, SHARING the globally warmed models.

    This is the concrete handle loader. It lazily imports the engine (so pod_agent
    stays torch-free until an actual swap happens) and injects the warm embedder /
    extractor / LLM clients from the model source — the crucial bit that keeps
    per-tenant memory flat instead of loading a fresh model per tenant.
    """
    from tracerag.db import TraceDB
    from tracerag.router import TraceRouter

    db = TraceDB(file_path)
    db.init_schema()
    router = TraceRouter(db)

    src = _model_source
    if src is not None:
        # reuse already-loaded model instances (glue-level; the engine is untouched)
        router._embedder = getattr(src, "_embedder", None)
        router._extractor = getattr(src, "_extractor", None)
        router._intent_llm = getattr(src, "_intent_llm", None)
        router._llm = getattr(src, "_llm", None)
    logger.info("loaded tenant graph org=%s from %s (models shared=%s)",
                org_id, file_path, src is not None)
    return router, db


@dataclass
class LoadedGraph:
    org_id: str
    artifact_id: Optional[str] = None
    version: Optional[int] = None
    path: Optional[str] = None
    db: Any = None       # opaque TraceDB
    router: Any = None   # opaque TraceRouter


class TenantDatabaseRegistry:
    def __init__(self) -> None:
        self._by_org: dict[str, LoadedGraph] = {}
        self._lock = threading.RLock()
        self._loader: Optional[HandleLoader] = None

    # -- handle loader injection ------------------------------------------------
    def set_handle_loader(self, loader: Optional[HandleLoader]) -> None:
        self._loader = loader

    # -- reads ------------------------------------------------------------------
    def loaded_artifact_id(self, org_id: str) -> Optional[str]:
        """The artifact_id this pod currently serves for the org (REALITY)."""
        with self._lock:
            g = self._by_org.get(org_id)
            return g.artifact_id if g else None

    def get_tenant(self, org_id: str) -> Optional[LoadedGraph]:
        with self._lock:
            return self._by_org.get(org_id)

    # alias kept for the name the routing/API layer uses
    get = get_tenant

    def get_db_for_tenant(self, org_id: str) -> Any:
        """The open TraceDB handle for an org, or None if not loaded here."""
        with self._lock:
            g = self._by_org.get(org_id)
            return g.db if g else None

    def get_router_for_tenant(self, org_id: str) -> Any:
        with self._lock:
            g = self._by_org.get(org_id)
            return g.router if g else None

    def orgs(self) -> list[str]:
        with self._lock:
            return list(self._by_org)

    # -- writes -----------------------------------------------------------------
    def bind(
        self, org_id: str, *, db: Any = None, router: Any = None,
        artifact_id: Optional[str] = None, version: Optional[int] = None,
        path: Optional[str] = None,
    ) -> Optional[LoadedGraph]:
        """Attach an already-open handle for an org (atomic). Returns the displaced
        entry (if any) for the caller to close."""
        new = LoadedGraph(org_id=org_id, artifact_id=artifact_id, version=version,
                          path=str(path) if path else None, db=db, router=router)
        with self._lock:
            old = self._by_org.get(org_id)
            self._by_org[org_id] = new
        return old

    def swap(
        self, org_id: str, artifact_id: str, version: int, path: str,
        *, db: Any = None, router: Any = None,
    ) -> Optional[LoadedGraph]:
        """Point an org at a freshly downloaded artifact. If a loader is set (and
        handles weren't supplied), open the real graph; else record the path only.
        Returns the displaced graph so the caller can close it."""
        if db is None and router is None and self._loader is not None:
            try:
                router, db = self._loader(org_id, path)
            except Exception:  # noqa: BLE001 — never let a bad load poison the map
                logger.exception("handle loader failed for org=%s path=%s", org_id, path)
                raise
        old = self.bind(org_id, db=db, router=router, artifact_id=artifact_id,
                        version=version, path=path)
        # close the graph we just displaced (opaque .close() if present)
        if old is not None and old.db is not None and old.db is not db:
            try:
                old.db.close()
            except Exception:  # noqa: BLE001
                logger.warning("closing displaced graph for org=%s failed", org_id)
        return old


# process-wide singleton — the ONE registry shared by the pod agent (writes),
# the API routers and the MCP provider (reads).
REGISTRY = TenantDatabaseRegistry()
