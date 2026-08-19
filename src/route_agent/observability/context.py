"""Request-scoped correlation ids shared by logs, traces, and Langfuse."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any

_run_id: ContextVar[str | None] = ContextVar("route_agent_run_id", default=None)
_request_id: ContextVar[str | None] = ContextVar("route_agent_request_id", default=None)
_job_id: ContextVar[str | None] = ContextVar("route_agent_job_id", default=None)
_source: ContextVar[str | None] = ContextVar("route_agent_source", default=None)
_command: ContextVar[str | None] = ContextVar("route_agent_command", default=None)


def new_run_id() -> str:
    return uuid.uuid4().hex


def current_run_id() -> str | None:
    return _run_id.get()


def current_request_id() -> str | None:
    return _request_id.get()


def current_job_id() -> str | None:
    return _job_id.get()


def current_source() -> str | None:
    return _source.get()


def current_command() -> str | None:
    return _command.get()


def current_context() -> dict[str, str | None]:
    return {
        "run_id": current_run_id(),
        "request_id": current_request_id(),
        "job_id": current_job_id(),
        "source": current_source(),
        "command": current_command(),
    }


def correlation_metadata() -> dict[str, str]:
    return {key: value for key, value in current_context().items() if value is not None}


@contextmanager
def bind_context(
    *,
    run_id: str | None = None,
    request_id: str | None = None,
    job_id: str | None = None,
    source: str | None = None,
    command: str | None = None,
) -> Iterator[dict[str, str | None]]:
    tokens: list[tuple[ContextVar[str | None], Token[str | None]]] = []
    updates: dict[ContextVar[str | None], str | None] = {
        _run_id: run_id,
        _request_id: request_id,
        _job_id: job_id,
        _source: source,
        _command: command,
    }
    for var, value in updates.items():
        if value is not None:
            tokens.append((var, var.set(value)))
    try:
        yield current_context()
    finally:
        for var, token in reversed(tokens):
            var.reset(token)


def snapshot_context() -> dict[str, Any]:
    return dict(current_context())
