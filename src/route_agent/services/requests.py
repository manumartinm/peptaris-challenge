"""Load and validate DesignRequest payloads without presentation concerns."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError as PydanticValidationError

from route_agent.models.events import PipelineEvent
from route_agent.models.request import DesignRequest
from route_agent.observe import PipelineObserver


class RequestLoadError(ValueError):
    """The request file or JSON payload cannot be turned into a DesignRequest."""

    def __init__(self, message: str, *, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


def parse_design_request(payload: object) -> DesignRequest:
    try:
        return DesignRequest.model_validate(payload)
    except PydanticValidationError as exc:
        raise RequestLoadError(
            "invalid DesignRequest",
            hint="unknown fields are rejected; check request_schema.json",
        ) from exc


def load_design_request_path(
    request_path: Path,
    observer: PipelineObserver | None = None,
) -> DesignRequest:
    _emit(
        observer,
        PipelineEvent(
            kind="stage_started",
            stage="loading",
            message=f"loading {request_path}",
        ),
    )
    if not request_path.is_file():
        raise RequestLoadError(
            "request file not found",
            hint="pass a DesignRequest JSON file; see route-agent validate --help",
        )
    try:
        payload = json.loads(request_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RequestLoadError(
            "invalid JSON",
            hint="the file must be a single JSON object",
        ) from exc
    request = parse_design_request(payload)
    _emit(
        observer,
        PipelineEvent(
            kind="stage_finished",
            stage="loading",
            request_id=request.request_id,
            message=request.request_id,
        ),
    )
    return request


def _emit(observer: PipelineObserver | None, event: PipelineEvent) -> None:
    if observer is not None:
        observer.on_event(event)
