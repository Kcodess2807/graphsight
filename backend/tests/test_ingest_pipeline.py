"""Prove the durable data layer: GitHub delta -> NLP -> graph-store Postgres, with
incremental (cursor) idempotency, structural tenant isolation, and the worker
reconcile wired to it. Torch-free: spaCy extractor + stub embedder injected.

Run:  python tests/test_ingest_pipeline.py   (from backend/)
"""
import os
import sys
import tempfile

_tmp = tempfile.mkdtemp(prefix="tracerag_ingest_")
os.environ["TENANT_DATA_DIR"] = os.path.join(_tmp, "td")
os.environ["GRAPH_STORE_DATABASE_URL"] = f"sqlite:///{os.path.join(_tmp, 'gs.db')}"
os.environ["CONTROL_PLANE_DATABASE_URL"] = f"sqlite:///{os.path.join(_tmp, 'cp.db')}"
os.environ["TRACERAG_GITHUB_MOCK"] = "1"   # hermetic: never touch the real GitHub API

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/

import logging
logging.disable(logging.CRITICAL)

from sqlmodel import Session, select

import models.control_plane as cp
import models.graph_store as gs
from models.graph_store import (
    EntityNode, count_edges_for_org, count_nodes_for_org, get_graph_store_engine,
    init_graph_store,
)
from tracerag import config
from tracerag.extract import EntityExtractor
from worker.ingestion.pipeline import run_incremental_ingest


def ok(m): print(f"  [OK] {m}", flush=True)


# torch-free injectables: spaCy NER + a deterministic stub embedder
spacy_extractor = EntityExtractor(prefer_gliner=False)


def stub_embed(text: str) -> list:
    seed = (abs(hash(text)) % 997) / 997.0
    return [round(seed, 4)] * config.EMBED_DIM


gs_engine = get_graph_store_engine()
init_graph_store(gs_engine)

ORG1, ORG2, REPO = "org_alpha", "org_beta", "repo-1"

print("1. First sync (empty cursor) -> GitHub delta -> NLP -> UPSERT")
r1 = run_incremental_ingest(ORG1, REPO, "acme/payments", None, gs_engine,
                            extractor=spacy_extractor, embed_fn=stub_embed)
print(f"     items={r1['items']} nodes={r1['nodes']} edges={r1['edges']} "
      f"cursor->{r1['new_cursor']}")
assert r1["items"] == 3 and r1["nodes"] > 0 and r1["edges"] > 0
assert r1["new_cursor"]
n1 = count_nodes_for_org(gs_engine, ORG1)
e1 = count_edges_for_org(gs_engine, ORG1)
ok(f"org_alpha now has {n1} nodes / {e1} edges in the graph store")

# the PR/issue item nodes and an author node must be present
with Session(gs_engine) as db:
    ids = {r.node_id: r for r in db.exec(
        select(EntityNode).where(EntityNode.org_id == ORG1)).all()}
labels = sorted({v.label for v in ids.values()})
print(f"     node labels present: {labels}")
assert f"{REPO}:pr:101" in ids and f"{REPO}:pr:102" in ids and f"{REPO}:issue:58" in ids
assert "ent:person:alice-dev" in ids
assert ids[f"{REPO}:pr:101"].properties.get("url", "").endswith("/pull/101")
assert len(ids[f"{REPO}:pr:101"].embedding) == config.EMBED_DIM
ok("PR/Issue item nodes, author node, JSON properties + embedding all persisted")

print("2. Incremental no-op: re-sync WITH the cursor -> nothing new")
r2 = run_incremental_ingest(ORG1, REPO, "acme/payments", r1["new_cursor"], gs_engine,
                            extractor=spacy_extractor, embed_fn=stub_embed)
assert r2["items"] == 0 and r2["nodes"] == 0
assert count_nodes_for_org(gs_engine, ORG1) == n1
ok("cursor present -> 0 items, node count unchanged (incremental works)")

print("3. Idempotent re-run from empty cursor -> UPSERT, no duplicates")
r3 = run_incremental_ingest(ORG1, REPO, "acme/payments", None, gs_engine,
                            extractor=spacy_extractor, embed_fn=stub_embed)
assert count_nodes_for_org(gs_engine, ORG1) == n1, "UPSERT created duplicates!"
assert count_edges_for_org(gs_engine, ORG1) == e1
ok("re-ingesting the same delta upserts in place (counts stable)")

print("4. Tenant isolation: ingest the SAME repo for a different org")
run_incremental_ingest(ORG2, REPO, "acme/payments", None, gs_engine,
                       extractor=spacy_extractor, embed_fn=stub_embed)
assert count_nodes_for_org(gs_engine, ORG1) == n1, "org_beta bled into org_alpha!"
with Session(gs_engine) as db:
    shared = db.exec(select(EntityNode).where(
        EntityNode.node_id == "ent:person:alice-dev")).all()
orgs = sorted(r.org_id for r in shared)
print(f"     node_id 'ent:person:alice-dev' exists under orgs: {orgs}")
assert orgs == [ORG1, ORG2], orgs      # same node_id, two orgs, zero collision
ok("identical node_id coexists per-org; composite PK blocks cross-tenant bleed")

print("5. Worker wiring: reconcile_org_to_head runs the REAL pipeline")
# inject the torch-free extractor/embedder as the pipeline's process defaults so
# _reconcile_core (which calls run_incremental_ingest without args) uses them.
import worker.ingestion.pipeline as pl
pl._extractor = spacy_extractor
pl._embedder = stub_embed
from worker.tasks import _reconcile_core

cp_engine = cp.get_control_plane_engine()
cp.init_control_plane(cp_engine)
with Session(cp_engine) as db:
    db.add(cp.Organization(org_id="org_wired", name="Wired"))
    db.add(cp.Repository(org_id="org_wired", external_id="1", name="acme/payments"))
    db.commit()

res = _reconcile_core("org_wired", cp_engine)
print(f"     reconcile -> {res['status']} v{res['version']} "
      f"artifact={res['artifact_id'][:8]}…")
assert res["status"] == "completed"
with Session(cp_engine) as db:
    art = db.get(cp.GraphArtifact, res["artifact_id"])
    org = db.get(cp.Organization, "org_wired")
    repo = db.exec(select(cp.Repository).where(
        cp.Repository.org_id == "org_wired")).one()
real_count = count_nodes_for_org(gs_engine, "org_wired")
print(f"     artifact.entity_count={art.entity_count}  graph_store_nodes={real_count}"
      f"  repo.cursor={repo.last_synced_cursor}")
assert art.entity_count == real_count > 0, (art.entity_count, real_count)
assert org.desired_artifact_id == res["artifact_id"]        # intent flipped
assert repo.last_synced_cursor and repo.last_synced_cursor != "HEAD-mock"
ok("reconcile: GitHub -> NLP -> graph store -> REAL entity_count -> register + flip")

print("\n=====================================================")
print("DURABLE DATA LAYER PROVEN — GitHub -> NLP -> Postgres graph store")
print("=====================================================")
