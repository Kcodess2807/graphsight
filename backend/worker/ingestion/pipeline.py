"""Incremental ingestion pipeline: GitHub delta -> NLP -> graph-store UPSERT.

For one repo: fetch items after its cursor, run each PR/issue's text through the
existing GLiNER/spaCy extractor, turn PRs/issues/authors/entities into nodes and
their relationships into edges, embed them, and UPSERT into the graph store. Only
the delta is processed; the store accumulates the org's full graph across syncs.

Entities and authors are org-shared nodes (repo_id = None) so the SAME
"PaymentService" mentioned in two repos merges into one node — this is what makes
cross-repo traversal native once compiled into the .lbug.

The extractor and embedder are injectable so tests can run the real spaCy path
(and a stub embedder) without loading GLiNER/torch.
"""

import logging
import re

from sqlmodel import Session

from models.graph_store import ensure_graph_store, upsert_edges, upsert_nodes
from tracerag import config
from worker.ingestion.github_client import GitHubDeltaClient

logger = logging.getLogger("tracerag.ingestion")

_extractor = None
_embedder = None


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-") or "x"


def _default_extractor():
    """Ingest-time extractor (GLiNER preferred, spaCy fallback), built once."""
    global _extractor
    if _extractor is None:
        from tracerag.extract import EntityExtractor

        _extractor = EntityExtractor(prefer_gliner=True)
    return _extractor


def _default_embed_fn():
    """Real MiniLM encoder, built once. Tests inject a stub to skip torch."""
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(config.EMBED_MODEL)

        def _embed(text: str) -> list:
            vec = model.encode(text, normalize_embeddings=True)
            return [float(x) for x in vec]

        _embedder = _embed
    return _embedder


def run_incremental_ingest(
    org_id: str,
    repo_id: str,
    repo_name: str,
    cursor: str | None,
    engine,
    *,
    github_token: str | None = None,
    extractor=None,
    embed_fn=None,
) -> dict:
    """Ingest one repo's delta into the graph store. Returns
    {new_cursor, nodes, edges, items}."""
    ensure_graph_store(engine)
    delta = GitHubDeltaClient(
        repo_name, cursor, token=github_token
    ).fetch_recent_prs_and_commits()
    if not delta.items:
        return {"new_cursor": cursor, "nodes": 0, "edges": 0, "items": 0}

    extractor = extractor or _default_extractor()
    embed_fn = embed_fn or _default_embed_fn()

    nodes: dict[str, dict] = {}
    edges: dict[tuple, dict] = {}

    def add_node(node_id, label, name, embed_text, *, repo=None, props=None):
        if node_id in nodes:
            return
        nodes[node_id] = {
            "org_id": org_id, "node_id": node_id, "repo_id": repo,
            "label": label, "name": name, "properties": props or {},
            "embedding": embed_fn(embed_text),
        }

    def add_edge(src, tgt, rel, weight):
        key = (src, tgt, rel)
        cur = edges.get(key)
        if cur is None or weight > cur["weight"]:
            edges[key] = {"org_id": org_id, "source_node_id": src,
                          "target_node_id": tgt, "relation_type": rel,
                          "weight": float(weight)}

    for item in delta.items:
        inode = f"{repo_id}:{item.kind.lower()}:{item.number}"
        add_node(inode, item.kind, f"{item.kind} #{item.number}",
                 f"{item.kind} #{item.number}: {item.title}. {item.body}",
                 repo=repo_id,
                 props={"title": item.title, "url": item.url,
                        "author": item.author, "external_id": item.external_id,
                        "merged": item.merged})

        # author is an org-shared Person node
        anode = f"ent:person:{_slug(item.author)}"
        add_node(anode, "Person", item.author, item.author)
        add_edge(inode, anode, "AUTHORED_BY", 1.0)

        # NLP-extracted entities (org-shared) + MENTIONS edges
        for ent in extractor.extract(f"{item.title}. {item.body}"):
            enode = f"ent:{_slug(ent.type)}:{_slug(ent.text)}"
            add_node(enode, ent.type, ent.text, ent.text)
            add_edge(inode, enode, "MENTIONS", round(float(ent.score), 4))

    with Session(engine) as db:
        n = upsert_nodes(db, list(nodes.values()))
        e = upsert_edges(db, list(edges.values()))
        db.commit()

    logger.info("ingest org=%s repo=%s: %d items -> %d nodes, %d edges (cursor -> %s)",
                org_id, repo_name, len(delta.items), n, e, delta.new_cursor)
    return {"new_cursor": delta.new_cursor, "nodes": n, "edges": e,
            "items": len(delta.items)}
