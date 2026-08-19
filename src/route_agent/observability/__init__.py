"""Observability: Loguru logging, correlation ids, and payload redaction."""

from __future__ import annotations

from route_agent.observability.config import (
    LogFormat,
    configure_logging,
    default_log_dir,
    env_log_format,
    env_verbose,
    format_json_record,
    log_level,
)
from route_agent.observability.context import (
    bind_context,
    correlation_metadata,
    current_command,
    current_context,
    current_job_id,
    current_request_id,
    current_run_id,
    current_source,
    new_run_id,
    snapshot_context,
)
from route_agent.observability.logger import StructuredLogger
from route_agent.observability.redaction import (
    hash_payload,
    payload_fields,
    payloads_enabled,
    redact_fields,
    truncate_text,
)

__all__ = [
    "LogFormat",
    "StructuredLogger",
    "bind_context",
    "configure_logging",
    "correlation_metadata",
    "current_command",
    "current_context",
    "current_job_id",
    "current_request_id",
    "current_run_id",
    "current_source",
    "default_log_dir",
    "env_log_format",
    "env_verbose",
    "format_json_record",
    "hash_payload",
    "log_level",
    "new_run_id",
    "payload_fields",
    "payloads_enabled",
    "redact_fields",
    "snapshot_context",
    "truncate_text",
]
