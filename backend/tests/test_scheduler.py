"""Multi-pod scheduler: least-loaded placement, graceful fallback, stale-pod
exclusion, boot-time hydration, and onboarding picking the least-loaded pod.
Network-free (registry runs loader-less, so no torch).

Run:  python tests/test_scheduler.py   (from backend/)
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

_tmp = tempfile.mkdtemp(prefix="tracerag_sched_")
os.environ["CONTROL_PLANE_DATABASE_URL"] = f"sqlite:///{os.path.join(_tmp, 'cp.db')}"
os.environ["TENANT_DATA_DIR"] = os.path.join(_tmp, "td")
os.environ["ADMIN_SECRET_KEY"] = "adm"
os.environ["POD_ID"] = "pod-local-dev"
from cryptography.fernet import Fernet
os.environ["ENCRYPTION_MASTER_KEY"] = Fernet.generate_key().decode()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/

import logging
logging.disable(logging.CRITICAL)

from sqlmodel import Session, select

import lifecycle
import models.control_plane as cp
import storage
from models.control_plane import (
    ArtifactStatus, GraphArtifact, LoadStatus, Organization, Pod, PodAssignment,
    PodStatus,
)
from registry import TenantDatabaseRegistry
from scheduler.placement import determine_optimal_pod


def ok(m): print(f"  [OK] {m}", flush=True)


engine = cp.get_control_plane_engine()
cp.init_control_plane(engine)


def add_pod(pid, heartbeat="fresh"):
    now = datetime.now(timezone.utc)
    hb = None if heartbeat == "none" else (
        now if heartbeat == "fresh" else now - timedelta(seconds=9999))
    with Session(engine) as db:
        db.add(Pod(pod_id=pid, ip="10.0.0.1", status=PodStatus.READY, last_heartbeat_at=hb))
        db.commit()


def assign(pid, org):
    with Session(engine) as db:
        db.add(Organization(org_id=org, name=org))
        db.add(PodAssignment(pod_id=pid, org_id=org, load_status=LoadStatus.PULLING))
        db.commit()


print("1. No healthy pods -> graceful fallback to local POD_ID")
with Session(engine) as db:
    assert determine_optimal_pod(db) == "pod-local-dev"
ok("empty fleet -> fallback pod-local-dev")

print("2. Least-loaded placement across a fleet")
add_pod("pod-A"); add_pod("pod-B"); add_pod("pod-C")
assign("pod-A", "o1"); assign("pod-A", "o2")   # A: 2
assign("pod-B", "o3")                           # B: 1
# C: 0
with Session(engine) as db:
    assert determine_optimal_pod(db) == "pod-C"
ok("A=2, B=1, C=0 -> picks pod-C (fewest tenants)")

print("3. Tie broken deterministically by pod_id")
assign("pod-C", "o4")                           # now B=1, C=1
with Session(engine) as db:
    assert determine_optimal_pod(db) == "pod-B"   # min(pod_id) among ties
ok("B=1, C=1 -> picks pod-B (stable tie-break)")

print("4. Stale-heartbeat pod is excluded")
add_pod("pod-STALE", heartbeat="stale")         # ready but old heartbeat
# give every fresh pod load so STALE (0) would win if it counted
assign("pod-B", "o5"); assign("pod-C", "o6")    # B=2, C=2, STALE=0
with Session(engine) as db:
    chosen = determine_optimal_pod(db)
assert chosen != "pod-STALE", chosen
ok(f"stale pod skipped despite 0 load (chose {chosen})")

print("5. Boot hydration: pod re-loads its READY tenants into the registry")
# publish a real artifact file into the mock bucket
dummy = storage.build_dir("oBOOT") / "v1.lbug"
dummy.write_text("MOCK LBUG boot")
s3_uri = storage.put_artifact(dummy, storage.artifact_key("oBOOT", 1))
with Session(engine) as db:
    db.add(Organization(org_id="oBOOT", name="Boot Org"))
    art = GraphArtifact(org_id="oBOOT", version=1, s3_uri=s3_uri,
                        status=ArtifactStatus.ACTIVE, entity_count=5)
    db.add(art); db.flush()
    art_id = art.artifact_id
    # this pod already serves oBOOT (ready); a second org is still 'pulling'
    db.add(PodAssignment(pod_id="pod-A", org_id="oBOOT",
                         loaded_artifact_id=art_id, load_status=LoadStatus.READY))
    db.add(Organization(org_id="oPULL", name="Pull Org"))
    db.add(PodAssignment(pod_id="pod-A", org_id="oPULL", load_status=LoadStatus.PULLING))
    db.commit()

reg = TenantDatabaseRegistry()   # loader-less -> path-only swap, no torch
with Session(engine) as db:
    hydrated = lifecycle.sync_pod_assignments_on_boot("pod-A", db, reg=reg)
orgs = {h["org_id"] for h in hydrated}
assert orgs == {"oBOOT"}, orgs                  # only READY rows hydrate
assert reg.get("oBOOT") is not None and reg.get("oPULL") is None
ok("boot loaded READY tenant (oBOOT) into registry; PULLING (oPULL) skipped")

print("6. register_pod is idempotent + sets ready/heartbeat")
with Session(engine) as db:
    lifecycle.register_pod("pod-A", db)         # already exists -> update
    pod = db.get(Pod, "pod-A")
assert pod.status == PodStatus.READY and pod.last_heartbeat_at is not None
ok("self-registration upserts pod as ready with a heartbeat")

print("7. Onboarding integration: provision assigns to the least-loaded pod")
import worker.tasks as tasks
tasks.request_reconcile = lambda org_id: None   # no Redis
from fastapi import FastAPI
from fastapi.testclient import TestClient
from routers import onboarding

# fresh fleet for a clean comparison: pod-X loaded, pod-Y empty
with Session(engine) as db:
    for r in db.exec(select(Pod)).all():
        db.delete(r)
    for r in db.exec(select(PodAssignment)).all():
        db.delete(r)
    db.commit()
add_pod("pod-X"); add_pod("pod-Y")
assign("pod-X", "seed-org")                     # X=1, Y=0

app = FastAPI(); app.include_router(onboarding.router)
client = TestClient(app)
r = client.post("/api/admin/onboarding/provision",
                headers={"X-Admin-Secret": "adm"},
                json={"tenant_name": "Elastic Inc", "repo_name": "acme/app"})
assert r.status_code == 200, r.text
assert r.json()["pod_id"] == "pod-Y", r.json()
ok("provision placed the new tenant on pod-Y (least-loaded)")

print("\n=====================================================")
print("SCHEDULER PROVEN — elastic least-loaded placement + boot hydration")
print("=====================================================")
