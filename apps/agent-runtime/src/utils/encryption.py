"""
Encryption utility: AES-256-GCM for sensitive data at rest.
Uses ENCRYPTION_KEY from environment.
Not a substitute for HashiCorp Vault but meets MVP security baseline.
"""
import base64
import os
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _get_key() -> bytes:
    key = os.getenv("ENCRYPTION_KEY", "change-this-to-another-random-string-32-chars")
    # Pad or truncate to 32 bytes for AES-256
    key_bytes = key.encode("utf-8")
    if len(key_bytes) < 32:
        key_bytes = key_bytes + b"\x00" * (32 - len(key_bytes))
    return key_bytes[:32]


def encrypt(value: str) -> str:
    """Encrypt a string value, return base64-encoded ciphertext with nonce."""
    if not value:
        return value
    key = _get_key()
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, value.encode("utf-8"), None)
    combined = nonce + ct
    return base64.b64encode(combined).decode("utf-8")


def decrypt(ciphertext: str) -> str:
    """Decrypt a base64-encoded ciphertext."""
    if not ciphertext:
        return ciphertext
    try:
        key = _get_key()
        combined = base64.b64decode(ciphertext.encode("utf-8"))
        nonce = combined[:12]
        ct = combined[12:]
        aesgcm = AESGCM(key)
        pt = aesgcm.decrypt(nonce, ct, None)
        return pt.decode("utf-8")
    except Exception:
        # If decryption fails, assume the value was not encrypted
        return ciphertext


def encrypt_dict_values(data: dict[str, Any], keys_to_encrypt: list[str]) -> dict[str, Any]:
    """Encrypt specific keys in a dict."""
    result = dict(data)
    for key in keys_to_encrypt:
        if key in result and isinstance(result[key], str) and result[key]:
            result[key] = encrypt(result[key])
    return result


def decrypt_dict_values(data: dict[str, Any], keys_to_decrypt: list[str]) -> dict[str, Any]:
    """Decrypt specific keys in a dict."""
    result = dict(data)
    for key in keys_to_decrypt:
        if key in result and isinstance(result[key], str) and result[key]:
            result[key] = decrypt(result[key])
    return result
