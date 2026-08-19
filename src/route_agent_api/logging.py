"""API process logging. Shared by the uvicorn entrypoint and app lifespan."""

from __future__ import annotations

import os

from route_agent.observability import (
    configure_logging,
    default_log_dir,
    env_log_format,
    env_verbose,
)


def configure_api_logging() -> None:
    raw = os.environ.get("ROUTE_AGENT_VERBOSE")
    verbose = 1 if raw is None or raw == "" else env_verbose()
    configure_logging(
        verbose=verbose,
        log_format=env_log_format(default="json"),
        log_dir=default_log_dir(),
    )
