from __future__ import annotations

from typing import Any

from route_agent.llm.langfuse_tracer import LangfuseTracer
from tests.support.validation_case import ValidationCase


class TestLangfuseAgentSpan(ValidationCase):
    def test_agent_run_uses_pipeline_root_observation_name(self) -> None:
        names: list[str] = []

        class Observation:
            def update(self, **_kwargs: object) -> None:
                return None

        class ObservationContext:
            def __enter__(self) -> Observation:
                return Observation()

            def __exit__(self, *_args: object) -> None:
                return None

        class Client:
            def start_as_current_observation(self, **kwargs: Any) -> ObservationContext:
                names.append(str(kwargs.get("name")))
                return ObservationContext()

            def flush(self) -> None:
                return None

        tracer = LangfuseTracer(public_key=None, secret_key=None, host=None)
        tracer._client = Client()  # type: ignore[assignment]
        metadata = {"node_type": "pipeline"}
        with tracer.start_run("REQ-01", metadata):
            pass

        assert names[0] == "route_agent_run"
