"""Active Langfuse/Fake run for nested generations and subprocess resume."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

_CURRENT_RUN: ContextVar[Any] = ContextVar("route_agent_langfuse_run", default=None)


def current_run() -> Any:
    return _CURRENT_RUN.get()


@contextmanager
def use_run(run: Any) -> Iterator[Any]:
    token = _CURRENT_RUN.set(run)
    try:
        yield run
    finally:
        _CURRENT_RUN.reset(token)


@contextmanager
def ensure_run(tracer: Any, request_id: str, metadata: dict[str, Any]) -> Iterator[Any]:
    current = tracer.current_run() if hasattr(tracer, "current_run") else None
    if current is not None:
        yield current
        return
    with tracer.start_run(request_id, metadata) as run:
        yield run
