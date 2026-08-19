"""In-memory single-worker job store. Presentation stays out of the core."""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter
from typing import Any

from route_agent.composition.wiring import build_route_pipeline, flush_tracers
from route_agent.models.events import PipelineEvent
from route_agent.models.request import DesignRequest
from route_agent.models.trace import PipelineTrace
from route_agent.observability import (
    StructuredLogger,
    bind_context,
    current_run_id,
    new_run_id,
)
from route_agent.settings import Settings
from route_agent_api.jobs.errors import (
    JobConflictError,
    TraceNotReadyError,
    UnknownJobError,
)
from route_agent_api.jobs.phases import apply_event_to_state, mark_complete
from route_agent_api.jobs.traces import list_stored_traces, load_trace
from route_agent_api.models import JobState, StoredTrace


class _JobRecord:
    def __init__(self, state: JobState, request: DesignRequest) -> None:
        self.state = state
        self.request = request
        self.trace: PipelineTrace | None = None


class JobObserver:
    """Translate core PipelineEvent values into job-store progress."""

    def __init__(self, store: JobStore, job_id: str) -> None:
        self._store = store
        self._job_id = job_id

    def on_event(self, event: PipelineEvent) -> None:
        self._store.apply_event(self._job_id, event)

    def close(self) -> None:
        return None


class JobStore:
    def __init__(self, jobs_trace_root: Path | None = None) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, _JobRecord] = {}
        self._active_id: str | None = None
        self._jobs_trace_root = jobs_trace_root or Path("traces") / "jobs"
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="route-job"
        )

    def health(self) -> dict[str, Any]:
        with self._lock:
            active = self._jobs.get(self._active_id) if self._active_id else None
            return {
                "active_job_id": self._active_id,
                "active_status": None if active is None else active.state.status,
            }

    def submit(self, request: DesignRequest, *, no_model: bool = False) -> JobState:
        job_id = str(uuid.uuid4())
        run_id = current_run_id() or new_run_id()
        state = JobState(
            job_id=job_id,
            request_id=request.request_id,
            status="queued",
            run_id=run_id,
        )
        record = _JobRecord(state, request)
        with self._lock:
            if self._has_active_locked():
                raise JobConflictError("A job is already running")
            self._jobs[job_id] = record
            self._active_id = job_id
        StructuredLogger("route_agent.api").info(
            "job_queued",
            job_id=job_id,
            request_id=request.request_id,
            run_id=run_id,
            no_model=no_model,
        )
        self._executor.submit(self._run, job_id, no_model, run_id)
        return state.model_copy()

    def get(self, job_id: str) -> JobState:
        with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                raise UnknownJobError(job_id)
            return record.state.model_copy(deep=True)

    def trace(self, job_id: str) -> PipelineTrace:
        with self._lock:
            record = self._jobs.get(job_id)
            if record is not None:
                if record.state.status != "completed" or record.trace is None:
                    raise TraceNotReadyError("Trace is not ready")
                return record.trace
        return load_trace(self._jobs_trace_root, job_id)

    def list_stored_traces(self) -> list[StoredTrace]:
        return list_stored_traces(self._jobs_trace_root)

    def apply_event(self, job_id: str, event: PipelineEvent) -> None:
        with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                return
            record.state = apply_event_to_state(record.state, event)

    def _run(self, job_id: str, no_model: bool, run_id: str) -> None:
        with self._lock:
            record = self._jobs[job_id]
        logger = StructuredLogger("route_agent.api")
        observer = JobObserver(self, job_id)
        started = perf_counter()
        with bind_context(
            run_id=run_id,
            job_id=job_id,
            request_id=record.request.request_id,
            source="api",
        ):
            try:
                with self._lock:
                    record.state.status = "running"
                settings = Settings(no_model=no_model)
                logger.info(
                    "job_running",
                    job_id=job_id,
                    request_id=record.request.request_id,
                    run_id=run_id,
                    model=settings.model,
                    reasoning_effort=settings.reasoning_effort,
                )
                trace_dir = self._jobs_trace_root / job_id
                result = build_route_pipeline(
                    settings, logger, trace_dir, observer=observer
                ).run(record.request)
                logger.info(
                    "job_completed",
                    job_id=job_id,
                    request_id=record.request.request_id,
                    run_id=run_id,
                    verdict=result.verdict.verdict,
                    duration_ms=round((perf_counter() - started) * 1000, 3),
                    trace_path=None
                    if result.trace_path is None
                    else str(result.trace_path),
                )
                with self._lock:
                    record.trace = result.trace
                    record.state.status = "completed"
                    record.state.phase = "assemble"
                    mark_complete(record.state, "assemble")
                    record.state.verdict = result.verdict.verdict
                    record.state.confidence = result.verdict.confidence
                    record.state.activity = result.verdict.verdict
                    if self._active_id == job_id:
                        self._active_id = None
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "job_failed",
                    job_id=job_id,
                    run_id=run_id,
                    error_type=type(exc).__name__,
                    error=str(exc),
                    duration_ms=round((perf_counter() - started) * 1000, 3),
                )
                with self._lock:
                    record.state.status = "failed"
                    record.state.error = f"{type(exc).__name__}: {exc}"
                    if self._active_id == job_id:
                        self._active_id = None
            finally:
                observer.close()
                flush_tracers()

    def _has_active_locked(self) -> bool:
        if self._active_id is None:
            return False
        record = self._jobs.get(self._active_id)
        return record is not None and record.state.status in {"queued", "running"}
