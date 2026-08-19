"""Job-store errors. Presentation stays out of the core."""

from __future__ import annotations


class JobConflictError(RuntimeError):
    """Another job is already queued or running."""


class UnknownJobError(KeyError):
    """The requested job_id is not in memory and has no file on disk."""


class TraceNotReadyError(RuntimeError):
    """The job exists but has not written a trace yet."""


class TraceFileError(RuntimeError):
    """A trace file exists on disk but cannot be parsed."""
