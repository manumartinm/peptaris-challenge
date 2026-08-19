"""Public HTTP contracts for local pipeline jobs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

JobStatusName = Literal["queued", "running", "completed", "failed"]
JobPhase = Literal["validate", "walk", "molecular", "intent", "judge", "assemble"]
JOB_PHASES: tuple[JobPhase, ...] = (
    "validate",
    "walk",
    "molecular",
    "intent",
    "judge",
    "assemble",
)


class JobProgress(BaseModel):
    current: int | None = None
    total: int | None = None
    label: str | None = None


class JobState(BaseModel):
    job_id: str
    request_id: str
    status: JobStatusName
    run_id: str | None = None
    phase: JobPhase | None = None
    completed_phases: list[JobPhase] = Field(default_factory=list)
    progress: JobProgress | None = None
    activity: str | None = None
    error: str | None = None
    verdict: str | None = None
    confidence: str | None = None


class JobAccepted(BaseModel):
    job_id: str
    status: JobStatusName
    request_id: str
    run_id: str | None = None


class StoredTrace(BaseModel):
    job_id: str
    request_id: str
    file_name: str
    parent_name: str | None = None
    verdict: str | None = None
    confidence: str | None = None
    modified_at: str


class StoredTraceList(BaseModel):
    traces: list[StoredTrace]
