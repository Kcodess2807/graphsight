"""LadybugDB connection and schema management.

LadybugDB is a Kùzu fork — identical Python API. Vectors (FLOAT[384]) and the
graph live in a single .lbug file.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Sequence

import ladybug as lb

from . import config

logger = logging.getLogger(__name__)


class TraceDB:
    """Thin wrapper over a LadybugDB connection: schema, upsert, edges, search."""

    def __init__(self, db_path: str | Path = config.DB_PATH) -> None:
        self.db_path = str(db_path)
        self._db = lb.Database(self.db_path)
        self._conn = lb.Connection(self._db)
        logger.info("Opened LadybugDB at %s", self.db_path)
        self._load_vector_extension()

    def execute(self, query: str, params: dict[str, Any] | None = None):
        return self._conn.execute(query, params or {})

    def _load_vector_extension(self) -> None:
        """Load the official VECTOR extension (needed for QUERY_VECTOR_INDEX).

        LOAD must run per session; INSTALL is a one-time download (needs net
        the first time). Best-effort: vector_search degrades gracefully if the
        extension is unavailable (e.g. offline cloud box before first install).
        """
        try:
            self.execute("LOAD VECTOR;")
        except Exception:  # noqa: BLE001 — not installed yet on this machine
            try:
                self.execute("INSTALL VECTOR;")
                self.execute("LOAD VECTOR;")
            except Exception as exc:  # noqa: BLE001
                logger.warning("VECTOR extension unavailable: %s", exc)

    # --- schema (idempotent) ------------------------------------------- #
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
        # NOTE: the HNSW index is deliberately NOT created here. This build's
        # vector index is static — once it exists the embedding property can no
        # longer be SET, which blocks ingestion writes. The index is (re)built
        # once after ingestion via build_vector_index() for query-time search.
        logger.info("Schema ready (node=%s, rel=%s)",
                    config.NODE_TABLE, config.REL_TABLE)

    def build_vector_index(self) -> None:
        """(Re)build the HNSW index over current Entity embeddings.

        Call AFTER all ingestion writes are done. Drops any existing index
        first so re-ingested data is included (the index does not auto-update).
        """
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

    # --- writes -------------------------------------------------------- #
    def upsert_node(
        self,
        node_id: str,
        label: str,
        node_type: str,
        embedding: Sequence[float],
    ) -> None:
        # No ON MATCH SET: a canonical node's label/embedding must never be
        # clobbered by a later, noisier surface form. Existing id => no-op.
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
        # Documents are raw source material, not canonical entities: refresh
        # content on re-ingestion so edited files/tickets reflect immediately.
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
        """Exact, case-insensitive match of entities by their label.

        Used for deterministic query-side entity linking (e.g. a query
        mentioning 'OPS-142' lands directly on that ticket node).
        """
        return self._records(self.execute(
            f"MATCH (e:{config.NODE_TABLE}) WHERE lower(e.label) = lower($label) "
            f"RETURN e.id AS id, e.label AS label, e.type AS type;",
            {"label": label},
        ))

    def node_exists(self, node_id: str) -> bool:
        rows = self._records(self.execute(
            f"MATCH (e:{config.NODE_TABLE} {{id: $id}}) RETURN e.id AS id LIMIT 1;",
            {"id": node_id},
        ))
        return len(rows) > 0

    # --- reads / search ------------------------------------------------ #
    def vector_search(
        self,
        query_embedding: Sequence[float],
        k: int = config.CURATION_TOP_K,
    ) -> list[dict[str, Any]]:
        """Top-k cosine neighbours; rows carry similarity = 1 - distance.

        Uses the native HNSW index, which must have been built first via
        build_vector_index(). Raises if the index/extension is absent — callers
        that run mid-ingest should not rely on this (curation dedups in-memory).
        """
        self._check_dim(query_embedding)
        result = self.execute(
            f"CALL QUERY_VECTOR_INDEX('{config.NODE_TABLE}', "
            f"'{config.VECTOR_INDEX}', $q, {int(k)}) "
            f"RETURN node.id AS id, node.label AS label, node.type AS type, "
            f"distance ORDER BY distance;",
            {"q": list(query_embedding)},
        )
        rows = []
        for r in self._records(result):
            distance = float(r["distance"])
            rows.append({
                "id": r["id"], "label": r["label"], "type": r["type"],
                "distance": distance, "similarity": 1.0 - distance,
            })
        return rows

    def neighbors(self, node_id: str, k: int = config.TOP_K_GRAPH) -> list[dict[str, Any]]:
        """One-hop graph neighbours, strongest edge first (deterministic order)."""
        result = self.execute(
            f"MATCH (a:{config.NODE_TABLE} {{id: $id}})"
            f"-[r:{config.REL_TABLE}]-(b:{config.NODE_TABLE}) "
            f"RETURN b.id AS id, b.label AS label, b.type AS type, "
            f"r.confidence AS confidence "
            f"ORDER BY r.confidence DESC, b.id ASC "
            f"LIMIT $k;",
            {"id": node_id, "k": k},
        )
        return self._records(result)

    def node_degree(self, node_id: str) -> int:
        """Distinct one-hop neighbour count — used to detect hub super-nodes."""
        rows = self._records(self.execute(
            f"MATCH (a:{config.NODE_TABLE} {{id: $id}})"
            f"-[r:{config.REL_TABLE}]-(b:{config.NODE_TABLE}) "
            f"RETURN count(DISTINCT b.id) AS d;",
            {"id": node_id},
        ))
        return int(rows[0]["d"]) if rows else 0

    def documents_for_entities(self, entity_ids: list[str]) -> dict[str, list[dict]]:
        """Fetch the chunk text of every Document that MENTIONS the given entities.

        Returns {entity_id: [{doc_id, path, content}, ...]}.
        """
        if not entity_ids:
            return {}
        rows = self._records(self.execute(
            f"MATCH (d:{config.DOC_TABLE})-[:{config.MENTIONS_TABLE}]->"
            f"(e:{config.NODE_TABLE}) "
            f"WHERE e.id IN $ids "
            f"RETURN e.id AS entity_id, d.id AS doc_id, d.path AS path, "
            f"d.content AS content;",
            {"ids": entity_ids},
        ))
        grouped: dict[str, list[dict]] = {}
        for r in rows:
            grouped.setdefault(r["entity_id"], []).append(
                {"doc_id": r["doc_id"], "path": r["path"], "content": r["content"]}
            )
        return grouped

    def subgraph(self, node_ids: list[str]) -> dict:
        """Requested nodes + their 1-hop neighbors + edges among that set.

        Bounds the payload so the UI never renders the whole graph. Each node
        carries a ``requested`` flag so the frontend can dim the neighbor
        (background) context around the active trace.
        Returns {"nodes": [{id,label,type,requested}], "edges": [{source,target,confidence}]}.
        """
        if not node_ids:
            return {"nodes": [], "edges": []}

        # 1-hop expansion (OPTIONAL so isolated requested nodes still appear).
        rows = self._records(self.execute(
            f"MATCH (a:{config.NODE_TABLE}) WHERE a.id IN $ids "
            f"OPTIONAL MATCH (a)-[:{config.REL_TABLE}]-(b:{config.NODE_TABLE}) "
            f"RETURN a.id AS a_id, a.label AS a_label, a.type AS a_type, "
            f"b.id AS b_id, b.label AS b_label, b.type AS b_type;",
            {"ids": node_ids},
        ))

        requested = set(node_ids)
        nodes: dict[str, dict] = {}

        def _add(nid, label, ntype):
            if nid is not None and nid not in nodes:
                nodes[nid] = {"id": nid, "label": label, "type": ntype,
                              "requested": nid in requested}

        for r in rows:
            _add(r["a_id"], r["a_label"], r["a_type"])
            _add(r["b_id"], r["b_label"], r["b_type"])

        # Edges strictly between visible nodes.
        all_ids = list(nodes)
        edge_rows = self._records(self.execute(
            f"MATCH (a:{config.NODE_TABLE})-[r:{config.REL_TABLE}]->"
            f"(b:{config.NODE_TABLE}) "
            f"WHERE a.id IN $ids AND b.id IN $ids "
            f"RETURN a.id AS source, b.id AS target, r.confidence AS confidence;",
            {"ids": all_ids},
        )) if all_ids else []
        edges = [
            {"source": r["source"], "target": r["target"],
             "confidence": r["confidence"]}
            for r in edge_rows
        ]
        return {"nodes": list(nodes.values()), "edges": edges}

    def count_nodes(self) -> int:
        rows = self._records(self.execute(
            f"MATCH (e:{config.NODE_TABLE}) RETURN count(e) AS n;"))
        return int(rows[0]["n"]) if rows else 0

    # --- helpers ------------------------------------------------------- #
    @staticmethod
    def _check_dim(embedding: Sequence[float]) -> None:
        if len(embedding) != config.EMBED_DIM:
            raise ValueError(
                f"Embedding has {len(embedding)} dims, expected {config.EMBED_DIM}."
            )

    @staticmethod
    def _records(result) -> list[dict[str, Any]]:
        return result.get_as_df().to_dict(orient="records")

    # --- lifecycle ----------------------------------------------------- #
    def close(self) -> None:
        for handle in (self._conn, self._db):
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
