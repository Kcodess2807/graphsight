"""Symmetric secret encryption (Fernet) for secrets at rest — e.g. per-tenant
GitHub tokens stored in the control plane.

Fails **closed**: every operation requires a valid ``ENCRYPTION_MASTER_KEY``
(a urlsafe-base64 32-byte Fernet key). If it's missing or malformed, we raise
``VaultError`` rather than silently storing/returning plaintext.

Generate a key:  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

import os

from cryptography.fernet import Fernet, InvalidToken

_ENV_KEY = "ENCRYPTION_MASTER_KEY"


class VaultError(RuntimeError):
    """Encryption/decryption could not be performed securely."""


def _fernet() -> Fernet:
    key = os.getenv(_ENV_KEY)
    if not key:
        raise VaultError(
            f"{_ENV_KEY} is not set; refusing to encrypt/decrypt secrets."
        )
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception as exc:  # invalid length / not base64
        raise VaultError(
            f"{_ENV_KEY} is invalid — expected a urlsafe-base64 32-byte Fernet key."
        ) from exc


def encrypt_token(plain_text: str) -> str:
    """Encrypt a secret; returns the ciphertext token (str). Raises VaultError if
    the master key is unavailable or the input is not a non-empty string."""
    if not isinstance(plain_text, str) or plain_text == "":
        raise VaultError("encrypt_token requires a non-empty string.")
    return _fernet().encrypt(plain_text.encode()).decode()


def decrypt_token(cipher_text: str) -> str:
    """Decrypt a ciphertext token back to plaintext. Raises VaultError on a wrong
    key or corrupt/forged data (never returns partial/garbage)."""
    if not isinstance(cipher_text, str) or cipher_text == "":
        raise VaultError("decrypt_token requires a non-empty ciphertext string.")
    try:
        return _fernet().decrypt(cipher_text.encode()).decode()
    except InvalidToken as exc:
        raise VaultError("could not decrypt token (wrong key or corrupt data).") from exc


def is_configured() -> bool:
    """True if a usable master key is present (for health checks / startup logs)."""
    try:
        _fernet()
        return True
    except VaultError:
        return False
