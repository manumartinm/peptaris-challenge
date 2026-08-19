from __future__ import annotations

import json
import logging
from io import StringIO
from pathlib import Path

import pytest

from route_agent.observability import (
    StructuredLogger,
    bind_context,
    configure_logging,
    current_context,
    env_verbose,
    new_run_id,
)


def _configure(
    *, verbose: int = 2, quiet: bool = False, log_dir: Path | None = None
) -> StringIO:
    stream = StringIO()
    configure_logging(
        verbose=verbose,
        quiet=quiet,
        log_format="json",
        stream=stream,
        log_dir=log_dir,
        enqueue=False,
    )
    return stream


def _records(stream: StringIO) -> list[dict[str, object]]:
    lines = [line for line in stream.getvalue().splitlines() if line.strip()]
    return [json.loads(line) for line in lines]


class TestConfigureLogging:
    def test_json_records_include_contract_fields(self) -> None:
        stream = _configure()
        with bind_context(run_id="run-1", request_id="REQ-01", source="cli"):
            StructuredLogger("route_agent.pipeline").info(
                "pipeline_start",
                stage="validating",
                duration_ms=12.5,
                status="ok",
            )
        record = _records(stream)[-1]
        for key in (
            "timestamp",
            "level",
            "logger",
            "message",
            "event",
            "component",
            "source",
            "run_id",
            "request_id",
            "job_id",
            "stage",
            "duration_ms",
            "status",
        ):
            assert key in record
        assert record["event"] == "pipeline_start"
        assert record["component"] == "route_agent.pipeline"
        assert record["run_id"] == "run-1"
        assert record["request_id"] == "REQ-01"
        assert record["source"] == "cli"
        assert record["stage"] == "validating"
        assert record["duration_ms"] == 12.5
        assert record["job_id"] is None

    def test_verbose_flag_maps_to_info_and_debug(self) -> None:
        stream = _configure(verbose=1)
        logger = StructuredLogger("route_agent.test")
        logger.info("visible")
        logger.debug("hidden")
        messages = [item["message"] for item in _records(stream)]
        assert "visible" in messages
        assert "hidden" not in messages

        stream = _configure(verbose=2)
        StructuredLogger("route_agent.test").debug("shown")
        assert any(item["message"] == "shown" for item in _records(stream))

    def test_quiet_keeps_errors_only(self) -> None:
        stream = _configure(verbose=2, quiet=True)
        logger = StructuredLogger("route_agent.test")
        logger.warning("nope")
        logger.error("boom")
        messages = [item["message"] for item in _records(stream)]
        assert messages == ["boom"]

    def test_trace_level_requires_vvv(self) -> None:
        stream = _configure(verbose=2)
        StructuredLogger("route_agent.test").trace("detail")
        assert _records(stream) == []
        stream = _configure(verbose=3)
        StructuredLogger("route_agent.test").trace("detail")
        assert _records(stream)[-1]["message"] == "detail"
        assert _records(stream)[-1]["level"] == "TRACE"

    def test_redacts_secrets_in_fields(self) -> None:
        stream = _configure()
        StructuredLogger("route_agent.test").info(
            "auth",
            api_key="sk-live",
            nested={"password": "x", "ok": 1},
        )
        record = _records(stream)[-1]
        assert record["api_key"] == "[redacted]"
        nested = record["nested"]
        assert isinstance(nested, dict)
        assert nested["password"] == "[redacted]"
        assert nested["ok"] == 1

    def test_writes_jsonl_when_log_dir_is_set(self, tmp_path: Path) -> None:
        stream = _configure(log_dir=tmp_path)
        StructuredLogger("route_agent.test").info("persisted", request_id="REQ")
        files = list(tmp_path.glob("*.jsonl"))
        assert files
        payload = files[0].read_text(encoding="utf-8")
        assert "persisted" in payload
        assert stream.getvalue()

    def test_intercepts_stdlib_logging(self) -> None:
        stream = _configure()
        logging.getLogger("uvicorn.error").error("uvicorn down")
        assert any(item["message"] == "uvicorn down" for item in _records(stream))

    def test_new_run_id_is_unique(self) -> None:
        assert new_run_id() != new_run_id()

    def test_bind_context_resets(self) -> None:
        with bind_context(run_id="a", source="cli"):
            assert current_context()["run_id"] == "a"
        assert current_context()["run_id"] is None

    def test_env_verbose_reads_integer(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ROUTE_AGENT_VERBOSE", raising=False)
        assert env_verbose() == 0
        monkeypatch.setenv("ROUTE_AGENT_VERBOSE", "2")
        assert env_verbose() == 2

    def test_env_log_format_defaults_and_rejects_unknown(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from route_agent.observability import env_log_format

        monkeypatch.delenv("ROUTE_AGENT_LOG_FORMAT", raising=False)
        assert env_log_format(default="json") == "json"
        monkeypatch.setenv("ROUTE_AGENT_LOG_FORMAT", "text")
        assert env_log_format() == "text"
        monkeypatch.setenv("ROUTE_AGENT_LOG_FORMAT", "xml")
        assert env_log_format(default="json") == "json"
