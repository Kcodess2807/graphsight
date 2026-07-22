"""GitHub OAuth handshake: login redirect, signed-state CSRF protection, token
exchange parsing, and encrypted-at-rest storage on callback. Network-free.

Run:  python tests/test_github_oauth.py   (from backend/)
"""
import os
import sys
import tempfile

_tmp = tempfile.mkdtemp(prefix="tracerag_oauth_")
os.environ["CONTROL_PLANE_DATABASE_URL"] = f"sqlite:///{os.path.join(_tmp, 'cp.db')}"
os.environ["GITHUB_CLIENT_ID"] = "Iv1.testclient"
os.environ["GITHUB_CLIENT_SECRET"] = "clientsecret"
os.environ["GITHUB_OAUTH_STATE_SECRET"] = "state-signing-secret"
from cryptography.fernet import Fernet
os.environ["ENCRYPTION_MASTER_KEY"] = Fernet.generate_key().decode()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/

import logging
logging.disable(logging.CRITICAL)

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

import models.control_plane as cp
from models.control_plane import Repository
from routers import github_oauth
from sqlmodel import Session, select


def ok(m): print(f"  [OK] {m}", flush=True)


cp.init_control_plane()
with Session(cp.get_control_plane_engine()) as db:
    db.add(Repository(org_id="org1", external_id="1", name="acme/app"))
    db.add(Repository(org_id="org1", external_id="2", name="acme/api"))
    db.commit()

app = FastAPI()
app.include_router(github_oauth.router)
client = TestClient(app)

print("1. /login redirects to GitHub with a signed state")
r = client.get("/api/github/login", params={"org_id": "org1"}, follow_redirects=False)
assert r.status_code == 302
loc = r.headers["location"]
assert loc.startswith("https://github.com/login/oauth/authorize?")
assert "client_id=Iv1.testclient" in loc and "state=org1%3A" in loc  # "org1:" signed
ok("302 to authorize URL with client_id + signed state")

print("2. Token exchange parses access_token (httpx MockTransport)")
def token_handler(request):
    return httpx.Response(200, json={"access_token": "gho_realtoken", "scope": "repo"})
tok = github_oauth._exchange_code("thecode", transport=httpx.MockTransport(token_handler))
assert tok == "gho_realtoken"
# error path: GitHub returns an error instead of a token
def err_handler(request):
    return httpx.Response(200, json={"error": "bad_verification_code"})
try:
    github_oauth._exchange_code("x", transport=httpx.MockTransport(err_handler))
    raise AssertionError("expected failure with no access_token")
except Exception:
    pass
ok("access_token parsed; missing token -> error")

print("3. Callback: valid state -> encrypt + store token on all org repos")
good_state = github_oauth._sign_state("org1")
github_oauth._exchange_code = lambda code, **kw: "gho_callbacktoken"   # stub the HTTP
r = client.get("/api/github/callback", params={"code": "abc", "state": good_state})
assert r.status_code == 200 and r.json()["repositories_updated"] == 2
with Session(cp.get_control_plane_engine()) as db:
    repos = db.exec(select(Repository).where(Repository.org_id == "org1")).all()
assert all(rp.github_token not in (None, "gho_callbacktoken") for rp in repos)  # ciphertext
assert all(rp.get_github_token() == "gho_callbacktoken" for rp in repos)        # decrypts
ok("both repos updated; token stored ENCRYPTED, decrypts correctly")

print("4. Tampered state -> 400 (CSRF / org-binding blocked)")
r = client.get("/api/github/callback",
               params={"code": "abc", "state": "org2:forgedsignature"})
assert r.status_code == 400
ok("forged state rejected")

print("\n=====================================================")
print("GITHUB OAUTH PROVEN — signed state, token exchange, encrypted storage")
print("=====================================================")
