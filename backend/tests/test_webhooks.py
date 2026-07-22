"""GitHub webhook listener: HMAC signature verification, merged-PR/push triggers,
multi-org fan-out, and fast 200 with backgrounded reconcile. Network-free.

Run:  python tests/test_webhooks.py   (from backend/)
"""
import hashlib
import hmac
import json
import os
import sys
import tempfile

_tmp = tempfile.mkdtemp(prefix="tracerag_wh_")
os.environ["CONTROL_PLANE_DATABASE_URL"] = f"sqlite:///{os.path.join(_tmp, 'cp.db')}"
os.environ["GITHUB_WEBHOOK_SECRET"] = "whsec_test_123"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/

import logging
logging.disable(logging.CRITICAL)

from fastapi import FastAPI
from fastapi.testclient import TestClient

import models.control_plane as cp
from models.control_plane import Repository
from sqlmodel import Session
from tracerag import config

SECRET = "whsec_test_123"


def ok(m): print(f"  [OK] {m}", flush=True)


# capture reconcile arming (no Redis)
_armed = []
import worker.tasks as tasks
tasks.request_reconcile = lambda org_id: _armed.append(org_id)

cp.init_control_plane()
with Session(cp.get_control_plane_engine()) as db:
    # two orgs both track the same public repo
    db.add(Repository(org_id="org1", external_id="1", name="acme/app"))
    db.add(Repository(org_id="org2", external_id="1", name="acme/app"))
    db.add(Repository(org_id="org3", external_id="1", name="other/repo"))
    db.commit()

from routers import webhooks
app = FastAPI()
app.include_router(webhooks.router)
client = TestClient(app)
URL = "/api/webhooks/github"


def sign(body: bytes) -> str:
    return "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


def post(event: str, payload: dict, *, sig=None, valid_sig=True):
    body = json.dumps(payload).encode()
    signature = sig if sig is not None else (sign(body) if valid_sig else "sha256=deadbeef")
    return client.post(URL, content=body, headers={
        "X-GitHub-Event": event, "X-Hub-Signature-256": signature,
        "Content-Type": "application/json",
    })


MERGED_PR = {"action": "closed", "pull_request": {"merged": True},
             "repository": {"full_name": "acme/app"}}

print("1. Valid signature + merged PR -> fan out to all orgs tracking the repo")
_armed.clear()
r = post("pull_request", MERGED_PR)
assert r.status_code == 200, r.text
assert r.json()["status"] == "accepted" and r.json()["orgs"] == 2
assert sorted(_armed) == ["org1", "org2"]      # backgrounded reconcile ran
ok(f"200 accepted; armed {sorted(_armed)} (org3 on a different repo untouched)")

print("2. Invalid signature -> 401, nothing armed")
_armed.clear()
r = post("pull_request", MERGED_PR, valid_sig=False)
assert r.status_code == 401 and _armed == []
ok("bad X-Hub-Signature-256 -> 401 (payload rejected)")

print("3. ping event -> pong")
assert post("ping", {"zen": "hi"}).json()["status"] == "pong"
ok("ping handled")

print("4. Closed-but-UNMERGED PR -> ignored")
_armed.clear()
r = post("pull_request", {"action": "closed", "pull_request": {"merged": False},
                          "repository": {"full_name": "acme/app"}})
assert r.status_code == 200 and "ignored" in r.json()["status"] and _armed == []
ok("unmerged close does not trigger ingestion")

print("5. push event on a known repo -> armed")
_armed.clear()
r = post("push", {"repository": {"full_name": "other/repo"}})
assert r.status_code == 200 and r.json()["orgs"] == 1 and _armed == ["org3"]
ok("push triggers reconcile for the tracking org")

print("6. Unknown repo -> accepted, zero orgs")
_armed.clear()
r = post("push", {"repository": {"full_name": "nobody/tracks-this"}})
assert r.status_code == 200 and r.json()["orgs"] == 0 and _armed == []
ok("untracked repo is a no-op")

print("7. No webhook secret configured -> 503 (never accept unverifiable)")
_saved = config.GITHUB_WEBHOOK_SECRET
config.GITHUB_WEBHOOK_SECRET = None
assert post("push", {"repository": {"full_name": "acme/app"}}).status_code == 503
config.GITHUB_WEBHOOK_SECRET = _saved
ok("missing secret -> 503")

print("\n=====================================================")
print("WEBHOOKS PROVEN — signed, verified, fanned out, fast 200")
print("=====================================================")
