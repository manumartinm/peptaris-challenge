"""CORS origins for the local Vite app and hosted Trace Explorer."""

from __future__ import annotations

import os

LOCAL_ORIGINS = (
    "http://127.0.0.1:5173",
    "http://localhost:5173",
)
DEFAULT_ORIGIN_REGEX = r"https://.*\.vercel\.app"


def cors_origins() -> list[str]:
    raw = os.environ.get("ROUTE_AGENT_CORS_ORIGINS", "")
    extra = [item.strip() for item in raw.split(",") if item.strip()]
    return [*LOCAL_ORIGINS, *extra]


def cors_origin_regex() -> str | None:
    if "ROUTE_AGENT_CORS_ORIGIN_REGEX" not in os.environ:
        return DEFAULT_ORIGIN_REGEX
    value = os.environ["ROUTE_AGENT_CORS_ORIGIN_REGEX"].strip()
    return value or None
