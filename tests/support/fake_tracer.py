from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from route_agent.llm.run_context import current_run, use_run


class FakeObservation:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def update(self, **kwargs: Any) -> None:
        self.payload.update(kwargs)


class FakeRun:
    def __init__(self, tracer: FakeTracer) -> None:
        self._tracer = tracer

    def trace_context(self) -> dict[str, str]:
        return {"trace_id": "a" * 32, "parent_span_id": "b" * 16}

    @contextmanager
    def span(
        self,
        name: str,
        metadata: dict[str, Any],
        **kwargs: Any,
    ) -> Iterator[FakeObservation]:
        payload = {"name": name, "metadata": metadata, **kwargs}
        self._tracer.spans.append(payload)
        yield FakeObservation(payload)

    @contextmanager
    def generation(
        self,
        name: str,
        metadata: dict[str, Any],
        **kwargs: Any,
    ) -> Iterator[FakeObservation]:
        payload = {"name": name, "metadata": metadata, **kwargs}
        self._tracer.generations.append(payload)
        yield FakeObservation(payload)


class FakeTracer:
    def __init__(self) -> None:
        self.runs: list[dict[str, Any]] = []
        self.spans: list[dict[str, Any]] = []
        self.generations: list[dict[str, Any]] = []
        self.continued: list[dict[str, Any]] = []
        self.flushed = 0
        self._current: FakeRun | None = None

    def flush(self) -> None:
        self.flushed += 1

    def current_run(self) -> FakeRun | None:
        return current_run() or self._current

    @contextmanager
    def start_run(self, request_id: str, metadata: dict[str, Any]) -> Iterator[FakeRun]:
        self.runs.append({"request_id": request_id, "metadata": metadata})
        run = FakeRun(self)
        self._current = run
        with use_run(run):
            yield run
        self._current = None

    @contextmanager
    def continue_span(
        self,
        name: str,
        metadata: dict[str, Any],
        trace_context: dict[str, str],
    ) -> Iterator[FakeRun]:
        self.continued.append(
            {"name": name, "metadata": metadata, "trace_context": trace_context}
        )
        run = FakeRun(self)
        self._current = run
        with use_run(run):
            yield run
        self._current = None
