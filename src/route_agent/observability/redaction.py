"""Secret stripping, truncation, and payload summaries for logs and traces."""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

SENSITIVE_FIELD_NAMES = {
    "api_key",
    "anthropic_api_key",
    "openai_api_key",
    "boltz_api_key",
    "langfuse_public_key",
    "langfuse_secret_key",
    "password",
    "secret",
    "token",
    "authorization",
    "key",
}

DEFAULT_PREVIEW_LIMIT = 240
DEFAULT_TEXT_LIMIT = 4000


def payloads_enabled() -> bool:
    return os.environ.get("ROUTE_AGENT_TRACE_PAYLOADS", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def redact_fields(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).lower() in SENSITIVE_FIELD_NAMES:
                redacted[str(key)] = "[redacted]"
            else:
                redacted[str(key)] = redact_fields(item)
        return redacted
    if isinstance(value, list):
        return [redact_fields(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_fields(item) for item in value)
    if hasattr(value, "model_dump") and callable(value.model_dump):
        return redact_fields(value.model_dump(mode="json"))
    return value


def truncate_text(value: str, *, limit: int = DEFAULT_TEXT_LIMIT) -> str:
    if len(value) <= limit:
        return value
    return f"{value[:limit]}…({len(value) - limit} more)"


def size_bytes(value: Any) -> int:
    if isinstance(value, str | bytes):
        return len(value.encode() if isinstance(value, str) else value)
    try:
        return len(json.dumps(value, sort_keys=True, default=str).encode("utf-8"))
    except TypeError:
        return len(str(value).encode("utf-8"))


def hash_payload(value: Any) -> str:
    encoded = json.dumps(redact_fields(value), sort_keys=True, default=str).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()[:16]


def preview_payload(value: Any, *, limit: int = DEFAULT_PREVIEW_LIMIT) -> str:
    if isinstance(value, str):
        return truncate_text(value, limit=limit)
    try:
        text = json.dumps(redact_fields(value), sort_keys=True, default=str)
    except TypeError:
        text = str(value)
    return truncate_text(text, limit=limit)


def payload_fields(value: Any, *, key: str = "payload") -> dict[str, Any]:
    """Return full redacted payload or a bounded summary, depending on env."""
    if payloads_enabled():
        return {key: redact_fields(value)}
    return {
        f"{key}_hash": hash_payload(value),
        f"{key}_bytes": size_bytes(value),
        f"{key}_preview": preview_payload(value),
    }
