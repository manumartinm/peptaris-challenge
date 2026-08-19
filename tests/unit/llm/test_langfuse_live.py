from __future__ import annotations

import os

import pytest

from route_agent.llm.langfuse_tracer import ROOT_OBSERVATION_NAME, LangfuseTracer
from route_agent.settings import Settings


@pytest.mark.live
def test_live_langfuse_single_root_with_generation() -> None:
    settings = Settings()
    public = settings.secret_value_or_none(settings.langfuse_public_key)
    secret = settings.secret_value_or_none(settings.langfuse_secret_key)
    if not public or not secret:
        pytest.skip("LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are required")

    tracer = LangfuseTracer(
        public_key=public,
        secret_key=secret,
        host=settings.langfuse_host or os.environ.get("LANGFUSE_HOST"),
    )
    if tracer._client is None:
        pytest.skip(f"Langfuse client unavailable: {tracer.last_error}")

    with tracer.start_run(
        "REQ-LIVE-TRACE",
        {"node_type": "pipeline", "source": "live-test"},
    ) as run:
        context = run.trace_context()
        with run.generation(
            "structure_request",
            {"model": "live-smoke"},
            model="live-smoke",
            input={"prompt": "ping"},
        ) as observation:
            observation.update(
                output={"text": "pong"},
                usage_details={"input": 1, "output": 1},
                cost_details={"total": 0.0},
            )
    tracer.flush()

    assert tracer.last_error is None
    assert context is not None
    assert context.get("trace_id")
    assert ROOT_OBSERVATION_NAME == "route_agent_run"
