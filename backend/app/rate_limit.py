"""Per-user and per-IP rate limiting for all API endpoints.

Uses in-memory sliding window counters. Resets on app restart,
which is acceptable for a single-instance deployment on Render.
"""
from __future__ import annotations

import time
import threading
from collections import defaultdict
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Rate limit definitions by endpoint group
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RateRule:
    max_requests: int
    window_seconds: float
    message: str = "Слишком много запросов. Подождите немного."


# Per-user limits (keyed by actor_id)
USER_LIMITS: dict[str, RateRule] = {
    "conversation_create": RateRule(5, 3600, "Вы создали слишком много чатов. Попробуйте позже."),
    "chat_expensive": RateRule(20, 60, "Слишком много сообщений. Подождите минуту."),
    "chat_transcribe": RateRule(10, 60, "Слишком много голосовых. Подождите минуту."),
    "conversation_manage": RateRule(30, 60, "Слишком много операций. Подождите минуту."),
    "conversation_read": RateRule(60, 60, "Слишком много запросов. Подождите."),
}

# Per-IP global limit (DDoS protection)
IP_LIMIT = RateRule(100, 60, "Слишком много запросов с вашего IP.")

# Endpoint → group mapping
ENDPOINT_GROUPS: dict[str, str] = {
    "/api/v1/conversations/start": "conversation_create",
    "/api/v1/chat/stream": "chat_expensive",
    "/api/v1/chat/voice": "chat_expensive",
    "/api/v1/chat/tts": "chat_expensive",
    "/api/v1/chat/transcribe": "chat_transcribe",
    "/api/v1/conversations/list": "conversation_read",
    "/api/v1/conversations/search": "conversation_read",
}

# Patterns for dynamic routes (conversations/{id}/action)
MANAGE_ACTIONS = {"archive", "unarchive", "rename", "delete"}
READ_ACTIONS = {"messages"}

# ---------------------------------------------------------------------------
# Sliding window counter
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_buckets: dict[str, list[float]] = defaultdict(list)

# Cleanup: remove old entries periodically
_CLEANUP_INTERVAL = 300  # 5 minutes
_last_cleanup = time.monotonic()


def _cleanup_old_entries() -> None:
    """Remove entries older than 1 hour from all buckets."""
    global _last_cleanup
    now = time.monotonic()
    if now - _last_cleanup < _CLEANUP_INTERVAL:
        return
    _last_cleanup = now
    cutoff = now - 3600
    keys_to_delete = []
    for key, timestamps in _buckets.items():
        _buckets[key] = [t for t in timestamps if t > cutoff]
        if not _buckets[key]:
            keys_to_delete.append(key)
    for key in keys_to_delete:
        del _buckets[key]


def check_rate_limit(key: str, rule: RateRule) -> tuple[bool, int]:
    """Check if key exceeds rate limit.

    Returns (allowed: bool, retry_after_seconds: int).
    """
    now = time.monotonic()
    bucket_key = f"{key}"

    with _lock:
        _cleanup_old_entries()
        timestamps = _buckets[bucket_key]
        cutoff = now - rule.window_seconds
        # Remove expired entries
        _buckets[bucket_key] = [t for t in timestamps if t > cutoff]
        timestamps = _buckets[bucket_key]

        if len(timestamps) >= rule.max_requests:
            # Calculate retry-after
            oldest = timestamps[0] if timestamps else now
            retry_after = int(rule.window_seconds - (now - oldest)) + 1
            return False, max(retry_after, 1)

        timestamps.append(now)
        return True, 0


def get_endpoint_group(path: str) -> str | None:
    """Determine rate limit group for a given path."""
    # Exact match first
    if path in ENDPOINT_GROUPS:
        return ENDPOINT_GROUPS[path]

    # Dynamic route: /api/v1/conversations/{id}/{action}
    parts = path.rstrip("/").split("/")
    if len(parts) >= 5 and parts[1] == "api" and parts[3] == "conversations":
        action = parts[-1]
        if action in MANAGE_ACTIONS:
            return "conversation_manage"
        if action in READ_ACTIONS:
            return "conversation_read"

    return None


def check_user_rate(actor_id: str, path: str) -> tuple[bool, str, int]:
    """Check per-user rate limit for endpoint.

    Returns (allowed, error_message, retry_after).
    """
    group = get_endpoint_group(path)
    if not group:
        return True, "", 0

    rule = USER_LIMITS.get(group)
    if not rule:
        return True, "", 0

    key = f"user:{actor_id}:{group}"
    allowed, retry_after = check_rate_limit(key, rule)
    if not allowed:
        return False, rule.message, retry_after
    return True, "", 0


def check_ip_rate(ip: str) -> tuple[bool, int]:
    """Check global per-IP rate limit.

    Returns (allowed, retry_after).
    """
    key = f"ip:{ip}"
    return check_rate_limit(key, IP_LIMIT)


def is_force_new_conversation(path: str, body: dict | None) -> bool:
    """Check if this is a force_new conversation creation request."""
    if path != "/api/v1/conversations/start":
        return False
    if body and body.get("force_new"):
        return True
    return False
