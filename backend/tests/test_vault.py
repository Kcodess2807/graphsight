"""Secrets vault + Repository encryption-at-rest: roundtrip, fail-closed on
missing/wrong key, and the model helpers store ciphertext only.

Run:  python tests/test_vault.py   (from backend/)
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/

import logging
logging.disable(logging.CRITICAL)

from cryptography.fernet import Fernet

from security import vault
from security.vault import VaultError


def ok(m): print(f"  [OK] {m}", flush=True)


KEY_A = Fernet.generate_key().decode()
KEY_B = Fernet.generate_key().decode()

print("1. Roundtrip encrypt/decrypt")
os.environ["ENCRYPTION_MASTER_KEY"] = KEY_A
secret = "ghp_supersecrettoken_123"
cipher = vault.encrypt_token(secret)
assert cipher != secret and secret not in cipher      # not plaintext
assert vault.decrypt_token(cipher) == secret
assert vault.is_configured() is True
ok("decrypt(encrypt(x)) == x, ciphertext hides plaintext")

print("2. Wrong key cannot decrypt (fails closed)")
os.environ["ENCRYPTION_MASTER_KEY"] = KEY_B
try:
    vault.decrypt_token(cipher)
    raise AssertionError("decrypt with wrong key should raise")
except VaultError:
    ok("wrong master key -> VaultError (no garbage returned)")

print("3. Missing master key raises (never silent plaintext)")
os.environ.pop("ENCRYPTION_MASTER_KEY", None)
for fn, arg in ((vault.encrypt_token, "x"), (vault.decrypt_token, cipher)):
    try:
        fn(arg)
        raise AssertionError("expected VaultError with no key")
    except VaultError:
        pass
assert vault.is_configured() is False
ok("no ENCRYPTION_MASTER_KEY -> encrypt & decrypt both raise")

print("4. Invalid key material raises")
os.environ["ENCRYPTION_MASTER_KEY"] = "not-a-valid-fernet-key"
try:
    vault.encrypt_token("x")
    raise AssertionError("expected VaultError for bad key")
except VaultError:
    ok("malformed key -> VaultError")

print("5. Repository stores ciphertext, decrypts on demand")
os.environ["ENCRYPTION_MASTER_KEY"] = KEY_A
os.environ["CONTROL_PLANE_DATABASE_URL"] = \
    f"sqlite:///{os.path.join(tempfile.mkdtemp(), 'cp.db')}"
import models.control_plane as cp
from models.control_plane import Repository
from sqlmodel import Session, select

cp.init_control_plane()
with Session(cp.get_control_plane_engine()) as db:
    r = Repository(org_id="org1", external_id="1", name="acme/app")
    r.set_github_token("ghp_tenanttoken")
    db.add(r)
    db.commit()

with Session(cp.get_control_plane_engine()) as db:
    row = db.exec(select(Repository).where(Repository.org_id == "org1")).one()
assert row.github_token not in (None, "ghp_tenanttoken")   # column is ciphertext
assert row.get_github_token() == "ghp_tenanttoken"         # decrypts
# None handling never needs the key
r2 = Repository(org_id="org2", external_id="2", name="acme/none")
r2.set_github_token(None)
assert r2.github_token is None and r2.get_github_token() is None
ok("Repository: column holds ciphertext, get_github_token() decrypts, None safe")

print("\n=====================================================")
print("VAULT PROVEN — secrets encrypted at rest, fail-closed without the key")
print("=====================================================")
