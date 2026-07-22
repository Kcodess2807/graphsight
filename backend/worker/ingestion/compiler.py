"""Phase 3 — the real graph compiler.

Reads an org's durable truth (EntityNode / EntityEdge) out of the graph-store
Postgres and builds the optimized, read-only ``.lbug`` artifact the pods serve:
nodes + embeddings + edges, then the HNSW vector index. The index build is the
CPU-heavy step we deliberately run HERE on the worker, never on a latency-critical
serving pod.

Memory discipline: nodes and edges are streamed from Postgres with ``yield_per``
(a server-side cursor on Postgres) and written straight into LadybugDB, so a
million-node org never materializes in RAM — only one batch at a time is resident.
"""

import logging
import shutil
from pathlib import Path

from sqlmodel import Session, select

from models.graph_store import EntityEdge, EntityNode
from tracerag.db import TraceDB

logger = logging.getLogger("tracerag.compiler")


def _prepare_fresh(path: Path) -> None:
    """Remove any prior file at ``path`` (and LadybugDB sidecars) so each version
    compiles from a clean slate — no stale nodes leaking across versions."""
    for p in (path, Path(f"{path}.wal"), Path(f"{path}-shm"), Path(f"{path}.tmp")):
        try:
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            elif p.exists():
                p.unlink()
        except OSError:  # pragma: no cover
            logger.warning("could not remove stale artifact piece: %s", p)


def _stream(session: Session, model, org_id: str, batch_size: int):
    """Yield an org's rows for ``model`` in batches (server-side cursor on PG)."""
    stmt = (
        select(model)
        .where(model.org_id == org_id)
        .execution_options(yield_per=batch_size)
    )
    yield from session.exec(stmt)


def compile_graph_for_org(
    org_id: str, db_engine, out_path, *, batch_size: int = 1000
) -> dict:
    """Compile org ``org_id``'s graph-store rows into a fresh ``.lbug`` at
    ``out_path``. Returns {path, entity_count, edge_count}.

    Order matters: all nodes first (so edges can MATCH their endpoints), then
    edges, then the HNSW index over the embeddings.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _prepare_fresh(out_path)

    db = TraceDB(out_path)
    db.init_schema()
    node_count = 0
    edge_count = 0
    try:
        with Session(db_engine) as gs:
            # --- Query + Build: nodes (streamed, written immediately) ---------
            for node in _stream(gs, EntityNode, org_id, batch_size):
                # graph-store (name, label) -> engine (label=display, type=kind)
                db.upsert_node(node.node_id, node.name, node.label, node.embedding)
                node_count += 1
            # --- edges (endpoints now exist, so MATCH…MERGE resolves) ---------
            for edge in _stream(gs, EntityEdge, org_id, batch_size):
                db.add_relationship(
                    edge.source_node_id, edge.target_node_id, float(edge.weight)
                )
                edge_count += 1

        # --- Index phase: HNSW over embeddings (CPU-heavy; worker-side) -------
        if node_count:
            db.build_vector_index()
    finally:
        db.close()   # flush to disk

    logger.info("compiled org=%s: %d nodes, %d edges -> %s",
                org_id, node_count, edge_count, out_path)
    return {"path": str(out_path), "entity_count": node_count, "edge_count": edge_count}
