"""END-TO-END SERVE DRY RUN — derisk the multi-tenant read path.

Proves a pod can, with NO restart:
  1. generate/register a real tenant .lbug,
  2. detect the assignment and pull+atomic-swap it into the live registry,
  3. share the globally warmed embedder/spaCy (no per-tenant model reload),
  4. serve a real /api/trace graph traversal on the dynamically loaded file.

Run:  python tests/test_e2e_serve.py   (from backend/)
"""
import os
import sys
import tempfile

# env before any project import (storage/config read env at import time)
_tmp = tempfile.mkdtemp(prefix="tracerag_e2e_")
os.environ["TENANT_DATA_DIR"] = os.path.join(_tmp, "td")
os.environ["CONTROL_PLANE_DATABASE_URL"] = f"sqlite:///{os.path.join(_tmp, 'cp.db')}"
os.environ["MULTI_TENANCY_ENABLED"] = "1"
os.environ["POD_ID"] = "pod-A"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/

import asyncio
import logging

logging.disable(logging.CRITICAL)

import models.control_plane as cp
from models.control_plane import (
    ApiKey, ArtifactStatus, GraphArtifact, LoadStatus, Organization, Pod,
    PodAssignment, get_control_plane_engine,
)
from sqlmodel import Session, select

import auth
import pod_agent
import registry
import storage
from middleware.routing import assignment_status
from scripts.generate_dry_run_artifact import build_dry_run_artifact
from tracerag.db import TraceDB
from tracerag.router import TraceRouter

ORG = "org_test"
POD = "pod-A"
RAW_KEY = "dryrun-secret-key"


def ok(msg):
    print(f"  [OK] {msg}", flush=True)


# --------------------------------------------------------------------------
print("1. Generate a REAL tiny .lbug artifact (5 nodes / 4 edges + HNSW)")
meta = build_dry_run_artifact(ORG, 1)
print(f"     s3_uri={meta['s3_uri']}  entities={meta['entity_count']}  "
      f"size={meta['size_bytes']}B")
assert meta["entity_count"] == 5
ok("artifact built + published to mock bucket")

# --------------------------------------------------------------------------
print("2. Warm the shared model source (one embedder for all tenants)")
build_path = storage.build_dir(ORG) / "dryrun_v1.lbug"
primary_db = TraceDB(build_path)
primary_router = TraceRouter(primary_db)
primary_router.embed_query("warmup")          # loads the single MiniLM
try:
    primary_router._get_extractor().extract("warmup")  # loads spaCy
except Exception:
    pass
registry.set_model_source(primary_router)
registry.REGISTRY.set_handle_loader(registry.default_tenant_loader)
ok("global embedder warmed + registered as model source")

# --------------------------------------------------------------------------
print("3. Seed the Control Plane (Org, Artifact, ApiKey, Pod, PodAssignment)")
engine = get_control_plane_engine()
cp.init_control_plane(engine)
with Session(engine) as db:
    db.add(Organization(org_id=ORG, name="Test Tenant"))
    art = GraphArtifact(
        org_id=ORG, version=1, s3_uri=meta["s3_uri"],
        checksum_sha256=meta["checksum_sha256"], size_bytes=meta["size_bytes"],
        entity_count=meta["entity_count"], status=ArtifactStatus.READY,
    )
    db.add(art)
    db.flush()
    artifact_id = art.artifact_id
    org = db.get(Organization, ORG)
    org.desired_artifact_id = artifact_id           # INTENT points at v1
    db.add(org)
    db.add(ApiKey(org_id=ORG, hashed_key=auth.hash_api_key(RAW_KEY), prefix=RAW_KEY[:8]))
    db.add(Pod(pod_id=POD, ip="10.0.0.1", status="ready"))
    db.add(PodAssignment(pod_id=POD, org_id=ORG, load_status=LoadStatus.PULLING))
    db.commit()
ok(f"seeded; desired_artifact_id={artifact_id[:8]}…, loaded=None (pulling)")

# --------------------------------------------------------------------------
print("4. Pod agent polls -> detects desired != loaded -> pull + atomic swap")
changes = pod_agent.reconcile_assignments(engine, pod_id=POD)
assert changes and changes[0]["to"] == artifact_id, changes
with Session(engine) as db:
    pa = db.exec(select(PodAssignment).where(
        PodAssignment.pod_id == POD, PodAssignment.org_id == ORG)).one()
    art_row = db.get(GraphArtifact, artifact_id)
assert pa.loaded_artifact_id == artifact_id and pa.load_status == LoadStatus.READY
assert art_row.status == ArtifactStatus.ACTIVE
ok("pod swapped v1 in; assignment.loaded == desired; artifact ACTIVE")

# --------------------------------------------------------------------------
print("5. Registry now serves the tenant — and SHARES the warm models")
tenant = registry.REGISTRY.get_tenant(ORG)
assert tenant is not None and tenant.db is not None and tenant.router is not None
assert tenant.router._embedder is primary_router._embedder, "embedder NOT shared!"
assert tenant.router._extractor is primary_router._extractor, "extractor NOT shared!"
ok("tenant graph loaded; embedder & spaCy are the SAME objects (no 2GB reload)")

# --------------------------------------------------------------------------
print("6. Auth + routing would admit the request")
assert auth.resolve_org_from_token(RAW_KEY) == ORG
verdict, detail = assignment_status(ORG, pod_id=POD)
assert verdict == "ready_here", (verdict, detail)
ok(f"API key -> {ORG}; routing verdict = ready_here on {POD}")

# --------------------------------------------------------------------------
print("7. Serve a REAL /api/trace on the dynamically loaded graph")
import api  # module import only (no lifespan/warm)

payload = asyncio.run(api.trace(
    api.TraceRequest(query="what fixed the payment bug?"),
    user_id="tester", org_id=ORG,
))
results = payload["results"]
labels = [r.get("label") for r in results]
print(f"     query returned {len(results)} nodes: {labels}")
assert len(results) > 0, "no results from the dynamically loaded graph!"
assert any(l in ("PaymentService", "Bug #7", "PR #42", "auth module", "Alice")
           for l in labels), labels
assert payload.get("context"), "no context assembled"
ok("real graph traversal executed on the on-the-fly tenant file")

print("\n=====================================================")
print("DRY RUN PASSED — pod physically served a dynamically loaded tenant")
print("=====================================================")

for h in (primary_db, tenant.db):
    try:
        h.close()
    except Exception:
        pass
