"""LadybugDB connection and schema management. LadybugDB is a Kuzu fork, same API."""

from __future__ import annotations

import logging
import queue
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

import ladybug as lb

from . import config

logger = logging.getLogger(__name__)


class TraceDB:
    """Wrapper over LadybugDB with a read-connection pool.

    LadybugDB (a Kuzu fork) parallelizes reads across *separate* connections — it
    releases the GIL in C++ — but a single connection serializes everything. So:

      * reads lease one of N pooled connections (``_fetch`` / ``_lease``), giving
        true read concurrency under load;
      * writes/DDL go through one dedicated connection under a lock, matching the
        engine's single-writer model (ingestion is single-threaded anyway).
    """

    def __init__(
        self, db_path: str | Path = config.DB_PATH, *, pool_size: int | None = None
    ) -> None:
        self.db_path = str(db_path)
        self._db = lb.Database(self.db_path)
        self._closed = False

        # dedicated write/DDL connection (single-writer); guarded by a lock
        self._write_lock = threading.Lock()
        self._write_conn = self._new_connection()

        # bounded pool of read connections; reads parallelize across them
        self._pool_size = max(1, config.DB_POOL_SIZE if pool_size is None else pool_size)
        self._pool: "queue.Queue" = queue.Queue(maxsize=self._pool_size)
        self._read_conns: list = []  # kept for clean shutdown
        for _ in range(self._pool_size):
            conn = self._new_connection()
            self._read_conns.append(conn)
            self._pool.put(conn)
        logger.info(
            "Opened LadybugDB at %s (read pool=%d)", self.db_path, self._pool_size
        )

    # ---- connection plumbing -------------------------------------------------

    def _new_connection(self):
        """Create a connection with the VECTOR extension loaded (per-connection)."""
        conn = lb.Connection(self._db)
        self._load_vector_on(conn)
        return conn

    @staticmethod
    def _load_vector_on(conn) -> None:
        """LOAD the VECTOR extension on a connection; INSTALL once if missing."""
        try:
            conn.execute("LOAD VECTOR;")
        except Exception:  # noqa: BLE001 — not installed yet on this machine
            try:
                conn.execute("INSTALL VECTOR;")
                conn.execute("LOAD VECTOR;")
            except Exception as exc:  # noqa: BLE001
                logger.warning("VECTOR extension unavailable: %s", exc)

    def _load_vector_extension(self) -> None:
        """Reload VECTOR on the write connection (used before index rebuilds)."""
        self._load_vector_on(self._write_conn)

    @contextmanager
    def _lease(self) -> Iterator[Any]:
        """Borrow a read connection from the pool, returning it on exit."""
        if self._closed:
            raise RuntimeError("TraceDB is closed")
        conn = self._pool.get(timeout=config.DB_POOL_TIMEOUT)
        try:
            yield conn
        finally:
            self._pool.put(conn)

    def execute(self, query: str, params: dict[str, Any] | None = None):
        """Write/DDL path: runs on the single write connection under a lock.

        Reads should use ``_fetch`` so they fan out across the pool; this is kept
        for schema, upserts and index builds (and any caller that ignores the
        result). The returned result must be consumed before the next write.
        """
        with self._write_lock:
            return self._write_conn.execute(query, params or {})

    def _fetch(
        self, query: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Read path: lease a pooled connection, run, materialize, release.

        Materializing (``get_as_df``) inside the lease is required — the result
        is bound to its connection, so it must be consumed before the connection
        goes back to the pool.
        """
        with self._lease() as conn:
            return self._records(conn.execute(query, params or {}))

    def init_schema(self) -> None:
        self.execute(
            f"CREATE NODE TABLE IF NOT EXISTS {config.NODE_TABLE} ("
            f"id STRING PRIMARY KEY, label STRING, type STRING, "
            f"embedding FLOAT[{config.EMBED_DIM}]);"
        )
        self.execute(
            f"CREATE NODE TABLE IF NOT EXISTS {config.DOC_TABLE} ("
            f"id STRING PRIMARY KEY, path STRING, content STRING);"
        )
        self.execute(
            f"CREATE REL TABLE IF NOT EXISTS {config.REL_TABLE} ("
            f"FROM {config.NODE_TABLE} TO {config.NODE_TABLE}, confidence DOUBLE);"
        )
        self.execute(
            f"CREATE REL TABLE IF NOT EXISTS {config.MENTIONS_TABLE} ("
            f"FROM {config.DOC_TABLE} TO {config.NODE_TABLE});"
        )
        # HNSW index built later via build_vector_index(); a live index blocks embedding writes
        logger.info("Schema ready (node=%s, rel=%s)",
                    config.NODE_TABLE, config.REL_TABLE)

    def build_vector_index(self) -> None:
        """(Re)build the HNSW index over current embeddings; call after ingestion."""
        self._load_vector_extension()
        try:
            self.execute(
                f"CALL DROP_VECTOR_INDEX('{config.NODE_TABLE}', "
                f"'{config.VECTOR_INDEX}');"
            )
        except Exception:  # noqa: BLE001 — no index to drop on first build
            pass
        self.execute(
            f"CALL CREATE_VECTOR_INDEX('{config.NODE_TABLE}', "
            f"'{config.VECTOR_INDEX}', 'embedding', metric := '{config.VECTOR_METRIC}');"
        )
        logger.info("Built vector index %s", config.VECTOR_INDEX)

    def upsert_node(
        self,
        node_id: str,
        label: str,
        node_type: str,
        embedding: Sequence[float],
    ) -> None:
        # no ON MATCH SET: never clobber a canonical node with a noisier surface form
        self._check_dim(embedding)
        self.execute(
            f"MERGE (e:{config.NODE_TABLE} {{id: $id}}) "
            f"ON CREATE SET e.label = $label, e.type = $type, e.embedding = $embedding",
            {"id": node_id, "label": label, "type": node_type,
             "embedding": list(embedding)},
        )

    def add_relationship(self, from_id: str, to_id: str, confidence: float = 1.0) -> None:
        self.execute(
            f"MATCH (a:{config.NODE_TABLE} {{id: $from_id}}), "
            f"(b:{config.NODE_TABLE} {{id: $to_id}}) "
            f"MERGE (a)-[r:{config.REL_TABLE}]->(b) ON CREATE SET r.confidence = $confidence",
            {"from_id": from_id, "to_id": to_id, "confidence": confidence},
        )

    def upsert_document(
        self, doc_id: str, content: str | None = None, path: str | None = None
    ) -> None:
        # documents are raw source, not canonical: refresh content on re-ingestion
        self.execute(
            f"MERGE (d:{config.DOC_TABLE} {{id: $id}}) "
            f"ON CREATE SET d.path = $path, d.content = $content "
            f"ON MATCH  SET d.path = $path, d.content = $content",
            {"id": doc_id, "path": path or doc_id, "content": content or ""},
        )

    def add_mention(self, doc_id: str, entity_id: str) -> None:
        self.execute(
            f"MATCH (d:{config.DOC_TABLE} {{id: $doc_id}}), "
            f"(e:{config.NODE_TABLE} {{id: $entity_id}}) "
            f"MERGE (d)-[:{config.MENTIONS_TABLE}]->(e)",
            {"doc_id": doc_id, "entity_id": entity_id},
        )

    def find_nodes_by_label(self, label: str) -> list[dict[str, Any]]:
        """Exact, case-insensitive match of entities by their label."""
        return self._fetch(
            f"MATCH (e:{config.NODE_TABLE}) WHERE lower(e.label) = lower($label) "
            f"RETURN e.id AS id, e.label AS label, e.type AS type;",
            {"label": label},
        )

    def node_exists(self, node_id: str) -> bool:
        rows = self._fetch(
            f"MATCH (e:{config.NODE_TABLE} {{id: $id}}) RETURN e.id AS id LIMIT 1;",
            {"id": node_id},
        )
        return len(rows) > 0

    def vector_search(
        self,
        query_embedding: Sequence[float],
        k: int = config.CURATION_TOP_K,
    ) -> list[dict[str, Any]]:
        """Top-k cosine neighbours via the HNSW index; similarity = 1 - distance."""
        self._check_dim(query_embedding)
        result = self._fetch(
            f"CALL QUERY_VECTOR_INDEX('{config.NODE_TABLE}', "
            f"'{config.VECTOR_INDEX}', $q, {int(k)}) "
            f"RETURN node.id AS id, node.label AS label, node.type AS type, "
            f"distance ORDER BY distance;",
            {"q": list(query_embedding)},
        )
        rows = []
        for r in result:
            distance = float(r["distance"])
            rows.append({
                "id": r["id"], "label": r["label"], "type": r["type"],
                "distance": distance, "similarity": 1.0 - distance,
            })
        return rows

    def neighbors(self, node_id: str, k: int = config.TOP_K_GRAPH) -> list[dict[str, Any]]:
        """One-hop graph neighbours, strongest edge first (deterministic order)."""
        return self._fetch(
            f"MATCH (a:{config.NODE_TABLE} {{id: $id}})"
            f"-[r:{config.REL_TABLE}]-(b:{config.NODE_TABLE}) "
            f"RETURN b.id AS id, b.label AS label, b.type AS type, "
            f"r.confidence AS confidence "
            f"ORDER BY r.confidence DESC, b.id ASC "
            f"LIMIT $k;",
            {"id": node_id, "k": k},
        )

    def node_degree(self, node_id: str) -> int:
        """Distinct one-hop neighbour count — used to detect hub super-nodes."""
        rows = self._fetch(
            f"MATCH (a:{config.NODE_TABLE} {{id: $id}})"
            f"-[r:{config.REL_TABLE}]-(b:{config.NODE_TABLE}) "
            f"RETURN count(DISTINCT b.id) AS d;",
            {"id": node_id},
        )
        return int(rows[0]["d"]) if rows else 0

    def expand_frontier(
        self, node_ids: list[str], k: int, max_degree: int
    ) -> dict[str, list[dict[str, Any]]]:
        """Batched 1-hop expansion of a whole frontier in one query (avoids N+1)."""
        if not node_ids:
            return {}
        rows = self._fetch(
            f"MATCH (a:{config.NODE_TABLE}) WHERE a.id IN $ids "
            f"OPTIONAL MATCH (a)-[r:{config.REL_TABLE}]-(b:{config.NODE_TABLE}) "
            f"RETURN a.id AS from_id, b.id AS to_id, b.label AS label, "
            f"b.type AS type, r.confidence AS confidence;",
            {"ids": list(node_ids)},
        )
        grouped: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            if r["to_id"] is None:  # isolated node
                continue
            grouped.setdefault(r["from_id"], []).append({
                "id": r["to_id"], "label": r["label"], "type": r["type"],
                "confidence": float(r["confidence"])
                if r["confidence"] is not None else 1.0,
            })
        out: dict[str, list[dict[str, Any]]] = {}
        for from_id, nbrs in grouped.items():
            if len({n["id"] for n in nbrs}) > max_degree:
                continue  # hub: reached but not traversed through
            nbrs.sort(key=lambda n: (-n["confidence"], n["id"]))
            out[from_id] = nbrs[:k]
        return out

    def documents_for_entities(self, entity_ids: list[str]) -> dict[str, list[dict]]:
        """Chunk text of every Document mentioning the given entities, keyed by entity id."""
        if not entity_ids:
            return {}
        rows = self._fetch(
            f"MATCH (d:{config.DOC_TABLE})-[:{config.MENTIONS_TABLE}]->"
            f"(e:{config.NODE_TABLE}) "
            f"WHERE e.id IN $ids "
            f"RETURN e.id AS entity_id, d.id AS doc_id, d.path AS path, "
            f"d.content AS content;",
            {"ids": entity_ids},
        )
        grouped: dict[str, list[dict]] = {}
        for r in rows:
            grouped.setdefault(r["entity_id"], []).append(
                {"doc_id": r["doc_id"], "path": r["path"], "content": r["content"]}
            )
        return grouped

    def subgraph(self, node_ids: list[str]) -> dict:
        """Requested nodes plus their 1-hop neighbors and the edges among that set."""
        if not node_ids:
            return {"nodes": [], "edges": []}

        # optional match so isolated requested nodes still appear
        rows = self._fetch(
            f"MATCH (a:{config.NODE_TABLE}) WHERE a.id IN $ids "
            f"OPTIONAL MATCH (a)-[:{config.REL_TABLE}]-(b:{config.NODE_TABLE}) "
            f"RETURN a.id AS a_id, a.label AS a_label, a.type AS a_type, "
            f"b.id AS b_id, b.label AS b_label, b.type AS b_type;",
            {"ids": node_ids},
        )

        requested = set(node_ids)
        nodes: dict[str, dict] = {}

        def _add(nid, label, ntype):
            if nid is not None and nid not in nodes:
                nodes[nid] = {"id": nid, "label": label, "type": ntype,
                              "requested": nid in requested}

        for r in rows:
            _add(r["a_id"], r["a_label"], r["a_type"])
            _add(r["b_id"], r["b_label"], r["b_type"])

        # edges strictly between visible nodes
        all_ids = list(nodes)
        edge_rows = self._fetch(
            f"MATCH (a:{config.NODE_TABLE})-[r:{config.REL_TABLE}]->"
            f"(b:{config.NODE_TABLE}) "
            f"WHERE a.id IN $ids AND b.id IN $ids "
            f"RETURN a.id AS source, b.id AS target, r.confidence AS confidence;",
            {"ids": all_ids},
        ) if all_ids else []
        edges = [
            {"source": r["source"], "target": r["target"],
             "confidence": r["confidence"]}
            for r in edge_rows
        ]
        return {"nodes": list(nodes.values()), "edges": edges}

    def count_nodes(self) -> int:
        rows = self._fetch(
            f"MATCH (e:{config.NODE_TABLE}) RETURN count(e) AS n;")
        return int(rows[0]["n"]) if rows else 0

    def top_entities(self, limit: int = 12) -> list[dict[str, Any]]:
        """Most-connected entities (highest distinct degree), with type."""
        # aggregate via WITH before ordering; ordering by a.label alongside the aggregate
        # fails in Kuzu ("Variable a is not in scope")
        return self._fetch(
            f"MATCH (a:{config.NODE_TABLE})-[r:{config.REL_TABLE}]-(b:{config.NODE_TABLE}) "
            f"WITH a, count(DISTINCT b) AS degree "
            f"RETURN a.id AS id, a.label AS label, a.type AS type, degree "
            f"ORDER BY degree DESC, a.label ASC "
            f"LIMIT $limit;",
            {"limit": int(limit)},
        )

    @staticmethod
    def _check_dim(embedding: Sequence[float]) -> None:
        if len(embedding) != config.EMBED_DIM:
            raise ValueError(
                f"Embedding has {len(embedding)} dims, expected {config.EMBED_DIM}."
            )

    @staticmethod
    def _records(result) -> list[dict[str, Any]]:
        return result.get_as_df().to_dict(orient="records")

    def close(self) -> None:
        """Drain the read pool and close every connection (idempotent).

        Safe across the hot-swap path: ``/api/graphs/switch`` builds a new
        TraceDB and closes the old one, so each pool is owned by exactly one
        TraceDB and never outlives it.
        """
        if self._closed:
            return
        self._closed = True
        handles = list(self._read_conns) + [self._write_conn, self._db]
        for handle in handles:
            try:
                handle.close()
            except Exception:  # noqa: BLE001
                pass
        logger.info("Closed LadybugDB at %s", self.db_path)

    def __enter__(self) -> "TraceDB":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def get_db(db_path: str | Path = config.DB_PATH, *, init: bool = True) -> TraceDB:
    db = TraceDB(db_path)
    if init:
        db.init_schema()
    return db
