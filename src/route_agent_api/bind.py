"""HTTP bind address. Local defaults stay loopback; Railway injects PORT."""

from __future__ import annotations

import os


def listen_host() -> str:
    return os.environ.get("ROUTE_AGENT_API_HOST", "127.0.0.1")


def listen_port() -> int:
    raw = os.environ.get("PORT") or os.environ.get("ROUTE_AGENT_API_PORT") or "8000"
    return int(raw)
