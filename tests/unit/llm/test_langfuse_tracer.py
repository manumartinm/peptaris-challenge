from __future__ import annotations

import pytest

from route_agent.llm.langfuse_tracer import LangfuseTracer
from tests.support.validation_case import ValidationCase


class TestLangfuseTracer(ValidationCase):
    def test_tracer_records_spans_without_raising_when_client_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class Boom:
            def __init__(self, **_kwargs: object) -> None:
                raise RuntimeError("langfuse down")

        monkeypatch.setattr("route_agent.llm.langfuse_tracer.Langfuse", Boom)
        tracer = LangfuseTracer(
            public_key="pk",
            secret_key="sk",
            host="http://localhost:3000",
        )
        with (
            tracer.start_run("REQ-01", {"stage": "validation"}) as run,
            run.span("validate_sequence", {"ok": True}),
        ):
            pass

        assert tracer.last_error is not None

    def test_disabled_tracer_is_noop(self) -> None:
        tracer = LangfuseTracer(public_key=None, secret_key=None, host=None)
        with tracer.start_run("REQ-01", {}) as run, run.span("validate_sequence", {}):
            pass
        assert tracer.last_error is None

    def test_flush_is_safe_when_disabled(self) -> None:
        tracer = LangfuseTracer(public_key=None, secret_key=None, host=None)
        tracer.flush()
        assert tracer.last_error is None

    def test_span_propagates_business_exceptions(self) -> None:
        class Observation:
            def update(self, **_kwargs: object) -> None:
                return None

        class ObservationContext:
            def __enter__(self) -> Observation:
                return Observation()

            def __exit__(self, *_args: object) -> None:
                return None

        class Client:
            def start_as_current_observation(
                self, **_kwargs: object
            ) -> ObservationContext:
                return ObservationContext()

            def flush(self) -> None:
                return None

        tracer = LangfuseTracer(public_key=None, secret_key=None, host=None)
        tracer._client = Client()  # type: ignore[assignment]
        with (
            pytest.raises(RuntimeError, match="boom"),
            tracer.start_run("REQ-01", {}) as run,
            run.span("validate_sequence", {}),
        ):
            raise RuntimeError("boom")

    def test_generation_passes_input_output_and_usage(self) -> None:
        updates: list[dict[str, object]] = []

        class Observation:
            def update(self, **kwargs: object) -> None:
                updates.append(dict(kwargs))

        class ObservationContext:
            def __enter__(self) -> Observation:
                return Observation()

            def __exit__(self, *_args: object) -> None:
                return None

        class Client:
            def start_as_current_observation(
                self, **kwargs: object
            ) -> ObservationContext:
                captured.append(dict(kwargs))
                return ObservationContext()

            def flush(self) -> None:
                return None

            def get_current_trace_id(self) -> str:
                return "a" * 32

            def get_current_observation_id(self) -> str:
                return "b" * 16

        captured: list[dict[str, object]] = []
        tracer = LangfuseTracer(public_key=None, secret_key=None, host=None)
        tracer._client = Client()  # type: ignore[assignment]
        with (
            tracer.start_run("REQ-01", {"node_type": "pipeline"}) as run,
            run.generation(
                "structure_request",
                {"model": "fake"},
                model="fake",
                input={"prompt": "hi"},
            ) as observation,
        ):
            observation.update(
                output={"text": "ok"},
                usage_details={"input": 1, "output": 2},
            )

        names = [item.get("name") for item in captured]
        assert names[0] == "route_agent_run"
        assert "structure_request" in names
        generation = next(
            item for item in captured if item.get("name") == "structure_request"
        )
        assert generation.get("as_type") == "generation"
        assert generation.get("input") is not None
        assert any("usage_details" in item for item in updates)
