"""Cryptographic utilities — Phase 13 (152-ФЗ compliance).

AES-256-GCM: шифрование ПДн в БД at rest.
HMAC-SHA256: криптографический audit trail LLM-вызовов.

Ключи берутся из env vars:
  PII_ENCRYPTION_KEY  — 32-байтовый hex (64 символа)
  LLM_AUDIT_HMAC_KEY  — произвольный секрет
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
from datetime import datetime, timezone

logger = logging.getLogger("crypto")

# ---------------------------------------------------------------------------
# Key loading
# ---------------------------------------------------------------------------

def _load_encryption_key() -> bytes | None:
    """Load AES-256 key from env PII_ENCRYPTION_KEY (64-char hex)."""
    raw = os.environ.get("PII_ENCRYPTION_KEY", "")
    if not raw:
        return None
    try:
        key = bytes.fromhex(raw.strip())
        if len(key) != 32:
            logger.warning("PII_ENCRYPTION_KEY must be 32 bytes (64 hex chars), got %d bytes", len(key))
            return None
        return key
    except ValueError:
        logger.warning("PII_ENCRYPTION_KEY is not valid hex")
        return None


def _load_hmac_key() -> bytes | None:
    raw = os.environ.get("LLM_AUDIT_HMAC_KEY", "")
    if not raw:
        return None
    return raw.encode()


# ---------------------------------------------------------------------------
# AES-256-GCM encrypt / decrypt
# ---------------------------------------------------------------------------

def encrypt(plaintext: str) -> str | None:
    """Encrypt plaintext with AES-256-GCM. Returns base64-encoded ciphertext.

    Format: base64(nonce[12] + ciphertext + tag[16])
    Returns None if encryption key not configured or cryptography not installed.
    """
    key = _load_encryption_key()
    if key is None:
        return None
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        aesgcm = AESGCM(key)
        nonce = secrets.token_bytes(12)
        ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        return base64.b64encode(nonce + ct).decode("ascii")
    except ImportError:
        logger.warning("cryptography package not installed — encryption disabled")
        return None
    except Exception:
        logger.warning("Encryption failed", exc_info=True)
        return None


def decrypt(ciphertext_b64: str) -> str | None:
    """Decrypt AES-256-GCM ciphertext. Returns plaintext or None on failure."""
    key = _load_encryption_key()
    if key is None:
        return None
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        raw = base64.b64decode(ciphertext_b64)
        nonce, ct = raw[:12], raw[12:]
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ct, None).decode("utf-8")
    except ImportError:
        logger.warning("cryptography package not installed — decryption disabled")
        return None
    except Exception:
        logger.warning("Decryption failed (wrong key or corrupted data)", exc_info=True)
        return None


def encrypt_json(data: dict | list | None) -> str | None:
    """Encrypt a JSON-serializable object. Returns encrypted base64 string or None."""
    if data is None:
        return None
    return encrypt(json.dumps(data, ensure_ascii=False))


def decrypt_json(ciphertext_b64: str | None) -> dict | list | None:
    """Decrypt and JSON-parse. Returns None on failure."""
    if not ciphertext_b64:
        return None
    plaintext = decrypt(ciphertext_b64)
    if plaintext is None:
        return None
    try:
        return json.loads(plaintext)
    except Exception:
        logger.warning("decrypt_json: failed to parse JSON after decryption")
        return None


# ---------------------------------------------------------------------------
# HMAC-SHA256 audit log
# ---------------------------------------------------------------------------

def compute_hmac(data: str) -> str:
    """Compute HMAC-SHA256 over data using LLM_AUDIT_HMAC_KEY.

    Returns hex digest, or empty string if key not configured.
    """
    key = _load_hmac_key()
    if key is None:
        return ""
    return hmac.new(key, data.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_hmac(data: str, expected_hex: str) -> bool:
    """Verify HMAC. Returns False if key not configured."""
    key = _load_hmac_key()
    if key is None:
        return False
    actual = hmac.new(key, data.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(actual, expected_hex)


def write_llm_audit_log(
    actor_id: str,
    model: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    pii_proxy_active: bool,
    role: str = "unknown",
) -> None:
    """Write a tamper-evident audit record for each LLM call (Phase 13).

    Record stored in agent_llm_audit_log table.
    HMAC computed over: actor_id|model|timestamp|pii_proxy_active
    """
    try:
        from app.db.pool import get_connection, has_pool
        if not has_pool():
            return
        ts = datetime.now(tz=timezone.utc).isoformat()
        canonical = f"{actor_id}|{model}|{ts}|{pii_proxy_active}"
        audit_hmac = compute_hmac(canonical)
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO agent_llm_audit_log
                      (actor_id, agent_role, model, prompt_tokens, completion_tokens,
                       pii_proxy_active, called_at, hmac)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (actor_id, role, model, prompt_tokens, completion_tokens,
                     pii_proxy_active, ts, audit_hmac),
                )
            conn.commit()
    except Exception:
        # Audit log failure must never break the main flow
        logger.debug("LLM audit log write failed", exc_info=True)
