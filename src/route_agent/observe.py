"""Observer protocol for pipeline progress. Chemistry stays independent of I/O.

This is the in-process event stream (`PipelineEvent`). Structured logs live in
``observability``. Persisted JSON traces live in ``trace``. Langfuse generations
are opened per real LLM attempt, not here.
"""

from __future__ import annotations

from typing import Protocol

from route_agent.models.events import PipelineEvent
from route_agent.observability import StructuredLogger


class PipelineObserver(Protocol):
    def on_event(self, event: PipelineEvent) -> None: ...

    def close(self) -> None: ...


class NoOpObserver:
    """Default observer used when ``--explain`` is off."""

    def on_event(self, event: PipelineEvent) -> None:
        return None

    def close(self) -> None:
        return None


class RecordingObserver:
    """Collect events for traces and tests."""

    def __init__(self) -> None:
        self.events: list[PipelineEvent] = []

    def on_event(self, event: PipelineEvent) -> None:
        self.events.append(event)

    def close(self) -> None:
        return None


class CompositeObserver:
    def __init__(self, *observers: PipelineObserver) -> None:
        self._observers = observers

    def on_event(self, event: PipelineEvent) -> None:
        for observer in self._observers:
            observer.on_event(event)

    def close(self) -> None:
        for observer in self._observers:
            observer.close()


class LoggingObserver:
    """Mirror pipeline events into structured logs."""

    def __init__(self, logger: StructuredLogger | None = None) -> None:
        self._logger = logger or StructuredLogger("route_agent.events")

    def on_event(self, event: PipelineEvent) -> None:
        self._logger.debug(
            f"pipeline_event_{event.kind}",
            kind=event.kind,
            stage=event.stage,
            request_id=event.request_id,
            node_id=event.node_id,
            parent_id=event.parent_id,
            family=event.family,
            process=event.process,
            site=event.site,
            status=event.status,
            reason=event.reason,
            duration_ms=event.duration_ms,
            calls=event.calls,
            cost_usd=event.cost_usd,
            current=event.current,
            total=event.total,
            detail=event.message,
            protecting_groups=(
                dict(event.diff.protecting_groups) if event.diff is not None else None
            ),
        )

    def close(self) -> None:
        return None
