"""Admin onboarding endpoint: secret guard, one-shot tenant provisioning, the
returned key authenticating, and reconcile arming. Network-free (Redis stubbed).

Run:  python tests/test_onboarding.py   (from backend/)
"""
import os
import sys
import tempfile

from cryptography.fernet import Fernet

_tmp = tempfile.mkdtemp(prefix="tracerag_onboard_")
os.environ["CONTROL_PLANE_DATABASE_URL"] = f"sqlite:///{os.path.join(_tmp, 'cp.db')}"
os.environ["ADMIN_SECRET_KEY"] = "top-secret-admin"
os.environ["POD_ID"] = "pod-A"
os.environ["ENCRYPTION_MASTER_KEY"] = Fernet.generate_key().decode()  # for token at rest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/

import logging
logging.disable(logging.CRITICAL)

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, select

import auth
import models.control_plane as cp
from models.control_plane import (
    ApiKey, LoadStatus, Organization, PodAssignment, Repository,
)
from routers import onboarding
from tracerag import config


def ok(m): print(f"  [OK] {m}", flush=True)


# stub Redis-backed reconcile arming so no broker is needed
_armed = []
import worker.tasks as tasks
tasks.request_reconcile = lambda org_id: _armed.append(org_id)

engine = cp.get_control_plane_engine()
cp.init_control_plane(engine)

app = FastAPI()
app.include_router(onboarding.router)
client = TestClient(app)

URL = "/api/admin/onboarding/provision"
PAYLOAD = {"tenant_name": "Acme Corp", "repo_name": "tiangolo/fastapi",
           "github_token": "ghp_faketoken123"}

print("1. Admin secret guard")
assert client.post(URL, json=PAYLOAD).status_code == 401                     # no header
assert client.post(URL, json=PAYLOAD,
                   headers={"X-Admin-Secret": "wrong"}).status_code == 401   # bad secret
ok("missing/incorrect X-Admin-Secret -> 401")

print("2. Provision a tenant (correct secret)")
r = client.post(URL, json=PAYLOAD, headers={"X-Admin-Secret": "top-secret-admin"})
assert r.status_code == 200, (r.status_code, r.text)
body = r.json()
print(f"     org_id={body['org_id']}  api_key={body['api_key'][:16]}…  "
      f"pod={body['pod_id']}  repo={body['repository_id'][:8]}…  "
      f"armed={body['reconcile_armed']}")
assert body["org_id"].startswith("org_")
assert body["api_key"].startswith("sk_live_")
assert body["pod_id"] == "pod-A"
assert body["repository_id"] and body["reconcile_armed"] is True
assert "save" in body["warning"].lower()
ok("200 with org_id, raw api_key, pod_id, repository_id, warning")

org_id, raw_key = body["org_id"], body["api_key"]

print("3. Control-plane rows created correctly (one transaction)")
with Session(engine) as db:
    org = db.get(Organization, org_id)
    keys = db.exec(select(ApiKey).where(ApiKey.org_id == org_id)).all()
    repo = db.exec(select(Repository).where(Repository.org_id == org_id)).one()
    pa = db.exec(select(PodAssignment).where(PodAssignment.org_id == org_id)).one()
assert org is not None and org.name == "Acme Corp"
assert len(keys) == 1 and keys[0].revoked_at is None
assert keys[0].hashed_key == auth.hash_api_key(raw_key)   # only the hash is stored
assert keys[0].prefix == raw_key[:12]
assert repo.name == "tiangolo/fastapi" and repo.last_synced_cursor is None
assert repo.github_token not in (None, "ghp_faketoken123")  # ENCRYPTED at rest
assert repo.get_github_token() == "ghp_faketoken123"        # decrypts correctly
assert pa.pod_id == "pod-A" and pa.load_status == LoadStatus.PULLING
ok("Organization + ApiKey(hash only) + Repository(cursor=None,token) + "
   "PodAssignment(pulling) all present")

print("4. The returned key actually authenticates to this org")
assert auth.resolve_org_from_token(raw_key) == org_id
ok("resolve_org_from_token(api_key) -> org_id (key is live)")

print("5. Reconcile was armed for the new org")
assert _armed == [org_id], _armed
ok("request_reconcile(org_id) invoked before responding")

print("6. Endpoint disabled when ADMIN_SECRET_KEY unset -> 503")
config.ADMIN_SECRET_KEY = None
assert client.post(URL, json=PAYLOAD,
                   headers={"X-Admin-Secret": "top-secret-admin"}).status_code == 503
config.ADMIN_SECRET_KEY = "top-secret-admin"
ok("no ADMIN_SECRET_KEY configured -> 503 (never open by accident)")

print("\n=====================================================")
print("ONBOARDING PROVEN — one call provisions a tenant + primes ingestion")
print("=====================================================")
