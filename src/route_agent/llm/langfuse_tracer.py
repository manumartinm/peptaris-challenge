from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from typing import Any

from langfuse import Langfuse, propagate_attributes
from langfuse.types import TraceContext

from route_agent.llm.run_context import current_run as active_run
from route_agent.llm.run_context import use_run
from route_agent.observability import StructuredLogger, correlation_metadata
from route_agent.observability.redaction import (
    payload_fields,
    payloads_enabled,
    redact_fields,
)

ROOT_OBSERVATION_NAME = "route_agent_run"


class _NullObservation:
    def update(self, **_kwargs: Any) -> None:
        return None


class _NullRun:
    def trace_context(self) -> dict[str, str] | None:
        return None

    @contextmanager
    def span(self, name: str, metadata: dict[str, Any], **kwargs: Any) -> Iterator[Any]:
        yield _NullObservation()

    @contextmanager
    def generation(
        self, name: str, metadata: dict[str, Any], **kwargs: Any
    ) -> Iterator[Any]:
        yield _NullObservation()


@contextmanager
def _observation_or_noop(context: Any) -> Iterator[Any]:
    observation = None
    entered = False
    try:
        observation = context.__enter__()
        entered = True
    except Exception:
        observation = None
    try:
        yield observation
    except BaseException:
        if entered:
            with suppress(Exception):
                context.__exit__(*sys.exc_info())
        raise
    else:
        if entered:
            with suppress(Exception):
                context.__exit__(None, None, None)


class LangfuseObservation:
    def __init__(self, observation: Any) -> None:
        self._observation = observation

    def update(self, **kwargs: Any) -> None:
        if self._observation is None or not kwargs:
            return
        payload = dict(kwargs)
        if "input" in payload:
            payload["input"] = sanitize_io(payload["input"])
        if "output" in payload:
            payload["output"] = sanitize_io(payload["output"])
        with suppress(Exception):
            self._observation.update(**payload)


class LangfuseRun:
    def __init__(self, client: Langfuse, observation: Any = None) -> None:
        self._client = client
        self._observation = observation

    def trace_context(self) -> dict[str, str] | None:
        try:
            trace_id = self._client.get_current_trace_id()
            observation_id = self._client.get_current_observation_id()
        except Exception:
            return None
        if not trace_id:
            return None
        context = {"trace_id": str(trace_id)}
        if observation_id:
            context["parent_span_id"] = str(observation_id)
        return context

    def span(
        self,
        name: str,
        metadata: dict[str, Any],
        **kwargs: Any,
    ) -> Any:
        return self._observation_cm("span", name, metadata, **kwargs)

    def generation(
        self,
        name: str,
        metadata: dict[str, Any],
        **kwargs: Any,
    ) -> Any:
        return self._observation_cm("generation", name, metadata, **kwargs)

    @contextmanager
    def _observation_cm(
        self,
        as_type: str,
        name: str,
        metadata: dict[str, Any],
        **kwargs: Any,
    ) -> Iterator[LangfuseObservation]:
        try:
            start_kwargs: dict[str, Any] = {"as_type": as_type, "name": name}
            model = kwargs.get("model") or metadata.get("model")
            if as_type == "generation" and model:
                start_kwargs["model"] = str(model)
            if kwargs.get("input") is not None:
                start_kwargs["input"] = sanitize_io(kwargs["input"])
            if kwargs.get("output") is not None:
                start_kwargs["output"] = sanitize_io(kwargs["output"])
            if kwargs.get("trace_context"):
                start_kwargs["trace_context"] = kwargs["trace_context"]
            context = self._client.start_as_current_observation(**start_kwargs)
        except Exception:
            yield LangfuseObservation(None)
            return
        with _observation_or_noop(context) as observation:
            wrapped = LangfuseObservation(observation)
            meta = {**correlation_metadata(), **metadata}
            wrapped.update(metadata=meta)
            yield wrapped


class LangfuseTracer:
    def __init__(
        self,
        public_key: str | None,
        secret_key: str | None,
        host: str | None,
        logger: StructuredLogger | None = None,
    ) -> None:
        self.last_error: Exception | None = None
        self._client: Langfuse | None = None
        self._logger = logger or StructuredLogger("route_agent.langfuse")
        if not public_key or not secret_key:
            return
        try:
            self._client = Langfuse(
                public_key=public_key,
                secret_key=secret_key,
                host=host,
            )
        except Exception as exc:  # noqa: BLE001
            self.last_error = exc
            self._logger.warning(
                "langfuse_unavailable", error_type=type(exc).__name__, error=str(exc)
            )

    def current_run(self) -> Any:
        return active_run()

    @contextmanager
    def start_run(self, request_id: str, metadata: dict[str, Any]) -> Iterator[Any]:
        if self._client is None:
            run = _NullRun()
            with use_run(run):
                yield run
            return
        merged = {**correlation_metadata(), "request_id": request_id, **metadata}
        try:
            context = self._client.start_as_current_observation(
                as_type="span",
                name=ROOT_OBSERVATION_NAME,
                metadata=merged,
            )
        except Exception as exc:  # noqa: BLE001
            self.last_error = exc
            self._logger.warning(
                "langfuse_span_failed", error_type=type(exc).__name__, error=str(exc)
            )
            yield _NullRun()
            return
        with _observation_or_noop(context) as observation:
            if observation is not None:
                with suppress(Exception):
                    observation.update(metadata=merged)
            lf_run = LangfuseRun(self._client, observation)
            try:
                attributes = propagate_attributes(
                    session_id=request_id,
                    metadata=merged,
                    tags=["route-agent", str(metadata.get("source") or "cli")],
                )
            except Exception as exc:  # noqa: BLE001
                self.last_error = exc
                with use_run(lf_run):
                    yield lf_run
                return
            with _observation_or_noop(attributes), use_run(lf_run):
                yield lf_run

    @contextmanager
    def continue_span(
        self,
        name: str,
        metadata: dict[str, Any],
        trace_context: dict[str, str],
    ) -> Iterator[Any]:
        if self._client is None:
            yield _NullRun()
            return
        merged = {**correlation_metadata(), **metadata}
        context_payload: TraceContext = {"trace_id": trace_context["trace_id"]}
        parent_span_id = trace_context.get("parent_span_id")
        if parent_span_id:
            context_payload["parent_span_id"] = parent_span_id
        try:
            context = self._client.start_as_current_observation(
                as_type="span",
                name=name,
                metadata=merged,
                trace_context=context_payload,
            )
        except Exception as exc:  # noqa: BLE001
            self.last_error = exc
            self._logger.warning(
                "langfuse_continue_failed",
                error_type=type(exc).__name__,
                error=str(exc),
            )
            yield _NullRun()
            return
        with _observation_or_noop(context) as observation:
            run = LangfuseRun(self._client, observation)
            with use_run(run):
                yield run
        self.flush()

    def flush(self) -> None:
        if self._client is None:
            return
        try:
            self._client.flush()
        except Exception as exc:  # noqa: BLE001
            self.last_error = exc
            self._logger.warning(
                "langfuse_flush_failed", error_type=type(exc).__name__, error=str(exc)
            )


def sanitize_io(value: Any) -> Any:
    if value is None:
        return None
    redacted = redact_fields(value)
    if payloads_enabled():
        return redacted
    return payload_fields(redacted, key="payload")


def current_run() -> Any:
    return active_run()
