"""One Langfuse generation per real model attempt."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from route_agent.llm.langfuse_tracer import _NullObservation
from route_agent.llm.run_context import current_run


@contextmanager
def trace_llm_generation(
    *,
    name: str,
    model: str,
    metadata: dict[str, Any],
    input_payload: object,
) -> Iterator[Any]:
    run = current_run()
    if run is None:
        yield _NullObservation()
        return
    with run.generation(
        name,
        {**metadata, "model": model},
        model=model,
        input=input_payload,
    ) as observation:
        try:
            yield observation
        except Exception as exc:
            observation.update(
                level="ERROR",
                output={"error": str(exc), "error_type": type(exc).__name__},
            )
            raise
