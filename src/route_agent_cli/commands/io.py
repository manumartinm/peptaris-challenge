"""Load requests and write JSON results. stdout is reserved for the payload."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

from route_agent.models.request import DesignRequest
from route_agent.observability import StructuredLogger
from route_agent.observe import PipelineObserver
from route_agent.services.requests import RequestLoadError, load_design_request_path
from route_agent_cli.commands.errors import exit_input


def load_design_request(
    request_path: Path,
    logger: StructuredLogger,
    observer: PipelineObserver | None = None,
) -> DesignRequest:
    logger.info("loading request", path=str(request_path))
    try:
        return load_design_request_path(request_path, observer)
    except RequestLoadError as exc:
        logger.error(exc.message, path=str(request_path), hint=exc.hint)
        exit_input()


def load_json_object(
    path: Path, logger: StructuredLogger, *, label: str
) -> dict[str, Any]:
    if not path.is_file():
        logger.error(f"{label} file not found", path=str(path))
        exit_input()
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logger.error(f"invalid {label} JSON", error=str(exc))
        exit_input()
    if not isinstance(loaded, dict):
        logger.error(f"{label} JSON must be an object")
        exit_input()
    return loaded


def write_or_echo_json(rendered: str, output: Path | None) -> None:
    if output is not None:
        output.write_text(rendered + "\n", encoding="utf-8")
        return
    click.echo(rendered)


def state_payload_from_object(loaded: dict[str, Any]) -> dict[str, Any]:
    state_payload = loaded.get("state", loaded)
    if isinstance(state_payload, dict) and "output" in state_payload:
        inner = state_payload["output"]
        return inner if isinstance(inner, dict) else {}
    return state_payload if isinstance(state_payload, dict) else {}
