"""Timed start/done/failed log events."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from time import perf_counter
from typing import Any

from route_agent.observability.logger import StructuredLogger


@contextmanager
def log_span(
    logger: StructuredLogger,
    event: str,
    **fields: Any,
) -> Iterator[dict[str, Any]]:
    started = perf_counter()
    logger.info(f"{event}_start", **fields)
    payload = dict(fields)
    try:
        yield payload
    except Exception as exc:
        logger.exception(
            f"{event}_failed",
            duration_ms=_elapsed_ms(started),
            error_type=type(exc).__name__,
            **fields,
        )
        raise
    else:
        extra = {key: value for key, value in payload.items() if key not in fields}
        logger.info(
            f"{event}_done",
            duration_ms=_elapsed_ms(started),
            status=payload.get("status", "ok"),
            **fields,
            **extra,
        )


def _elapsed_ms(started: float) -> float:
    return round((perf_counter() - started) * 1000, 3)
