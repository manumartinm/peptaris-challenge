"""In-memory single-worker job store. Presentation stays out of the core."""

from __future__ import annotations

from route_agent.composition.wiring import build_route_pipeline
from route_agent_api.jobs.errors import (
    JobConflictError,
    TraceFileError,
    TraceNotReadyError,
    UnknownJobError,
)
from route_agent_api.jobs.store import JobObserver, JobStore

__all__ = [
    "JobConflictError",
    "JobObserver",
    "JobStore",
    "TraceFileError",
    "TraceNotReadyError",
    "UnknownJobError",
    "build_route_pipeline",
]
