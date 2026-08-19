"""Shared CLI fixtures."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from click.testing import CliRunner

_OBSERVABILITY_ENV = (
    "ROUTE_AGENT_VERBOSE",
    "ROUTE_AGENT_LOG_DIR",
    "ROUTE_AGENT_LOG_FORMAT",
    "ROUTE_AGENT_TRACE_PAYLOADS",
)


@pytest.fixture(autouse=True)
def isolate_observability_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Keep CLI/API tests independent of a developer .env or shell."""
    for key in _OBSERVABILITY_ENV:
        monkeypatch.delenv(key, raising=False)
    yield


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()
