"""Read stored pipeline traces from disk."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from route_agent.models.trace import PipelineTrace
from route_agent_api.jobs.errors import TraceFileError, UnknownJobError
from route_agent_api.models import StoredTrace


def is_job_id(job_id: str) -> bool:
    try:
        uuid.UUID(job_id)
    except ValueError:
        return False
    return True


def newest_trace_file(job_dir: Path) -> Path | None:
    if not job_dir.is_dir():
        return None
    traces = [path for path in job_dir.glob("*.trace.json") if path.is_file()]
    if not traces:
        return None
    return max(traces, key=lambda path: path.stat().st_mtime)


def summary_from_trace_file(path: Path, job_id: str) -> StoredTrace | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    request = payload.get("request")
    verdict = payload.get("verdict")
    request_id = payload.get("request_id")
    if not isinstance(request_id, str) or not request_id:
        request_id = path.name.removesuffix(".trace.json")
    parent_name = None
    if isinstance(request, dict) and isinstance(request.get("parent_name"), str):
        parent_name = request["parent_name"]
    verdict_name = None
    confidence = None
    if isinstance(verdict, dict):
        if isinstance(verdict.get("verdict"), str):
            verdict_name = verdict["verdict"]
        if isinstance(verdict.get("confidence"), str):
            confidence = verdict["confidence"]
    modified = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    return StoredTrace(
        job_id=job_id,
        request_id=request_id,
        file_name=path.name,
        parent_name=parent_name,
        verdict=verdict_name,
        confidence=confidence,
        modified_at=modified.isoformat(),
    )


def list_stored_traces(jobs_trace_root: Path) -> list[StoredTrace]:
    if not jobs_trace_root.is_dir():
        return []
    items: list[StoredTrace] = []
    for job_dir in jobs_trace_root.iterdir():
        if not job_dir.is_dir() or not is_job_id(job_dir.name):
            continue
        path = newest_trace_file(job_dir)
        if path is None:
            continue
        summary = summary_from_trace_file(path, job_dir.name)
        if summary is not None:
            items.append(summary)
    items.sort(key=lambda item: item.modified_at, reverse=True)
    return items


def load_trace(jobs_trace_root: Path, job_id: str) -> PipelineTrace:
    if not is_job_id(job_id):
        raise UnknownJobError(job_id)
    path = newest_trace_file(jobs_trace_root / job_id)
    if path is None:
        raise UnknownJobError(job_id)
    try:
        return PipelineTrace.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        raise TraceFileError(f"Could not read trace for {job_id}") from exc
