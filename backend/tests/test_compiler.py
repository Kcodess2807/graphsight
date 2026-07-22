"""Phase 3 proof: compile the durable graph-store rows into a real, queryable
.lbug (nodes + edges + HNSW index), then reopen it and traverse/search. Torch-free
— embeddings come from Postgres, so the compiler needs no model.

Run:  python tests/test_compiler.py   (from backend/)
"""
import os
import sys
import tempfile

_tmp = tempfile.mkdtemp(prefix="tracerag_compile_")
os.environ["TENANT_DATA_DIR"] = os.path.join(_tmp, "td")
os.environ["GRAPH_STORE_DATABASE_URL"] = f"sqlite:///{os.path.join(_tmp, 'gs.db')}"
os.environ["TRACERAG_GITHUB_MOCK"] = "1"   # hermetic: never touch the real GitHub API

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/

import logging
logging.disable(logging.CRITICAL)

import storage
from models.graph_store import (
    count_edges_for_org, count_nodes_for_org, get_graph_store_engine, init_graph_store,
)
from tracerag import config
from tracerag.db import TraceDB
from tracerag.extract import EntityExtractor
from worker.ingestion.compiler import compile_graph_for_org
from worker.ingestion.pipeline import run_incremental_ingest


def ok(m): print(f"  [OK] {m}", flush=True)


def stub_embed(text: str) -> list:
    seed = (abs(hash(text)) % 997) / 997.0
    return [round(seed, 4)] * config.EMBED_DIM


ORG = "org_compile"
gs_engine = get_graph_store_engine()
init_graph_store(gs_engine)

print("1. Populate the durable graph store (GitHub -> NLP -> Postgres)")
run_incremental_ingest(ORG, "repo-1", "acme/payments", None, gs_engine,
                       extractor=EntityExtractor(prefer_gliner=False), embed_fn=stub_embed)
n_pg = count_nodes_for_org(gs_engine, ORG)
e_pg = count_edges_for_org(gs_engine, ORG)
print(f"     graph store: {n_pg} nodes, {e_pg} edges")
assert n_pg > 0 and e_pg > 0

print("2. Compile Postgres truth -> optimized .lbug (+ HNSW index)")
out = storage.build_dir(ORG) / "v1.lbug"
res = compile_graph_for_org(ORG, gs_engine, out)
print(f"     -> {res['entity_count']} nodes, {res['edge_count']} edges  path={res['path']}")
assert res["entity_count"] == n_pg, (res["entity_count"], n_pg)
assert res["edge_count"] == e_pg
assert os.path.exists(res["path"]) and os.path.getsize(res["path"]) > 0
ok(f"artifact compiled ({os.path.getsize(res['path'])} bytes); checksum "
   f"{storage.sha256_file(res['path'])[:12]}…")

print("3. Reopen the compiled .lbug and prove it is a real, queryable graph")
db = TraceDB(res["path"])
assert db.count_nodes() == n_pg, (db.count_nodes(), n_pg)
ok(f"reopened; count_nodes == {db.count_nodes()} (matches Postgres)")

# graph traversal: the PR node should have neighbors (author + mentioned entities)
nbrs = db.neighbors("repo-1:pr:101")
labels = [x["label"] for x in nbrs]
print(f"     neighbors of PR #101: {labels}")
assert len(nbrs) > 0, "compiled graph has no edges on the PR node!"
ok("edges compiled — graph traversal works on the artifact")

# vector index: HNSW query returns hits => the index was built into the file
hits = db.vector_search(stub_embed("PaymentService"), k=5)
print(f"     vector_search returned {len(hits)} hits: {[h['label'] for h in hits][:5]}")
assert len(hits) > 0, "HNSW index missing/empty in the compiled artifact!"
ok("HNSW index present — vector search works on the artifact")

db.close()

print("\n=====================================================")
print("PHASE 3 PROVEN — Postgres truth compiled into a real, queryable .lbug")
print("=====================================================")
