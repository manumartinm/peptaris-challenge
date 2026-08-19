"""Loguru configuration: stderr + optional rotating JSONL."""

from __future__ import annotations

import logging
import os
import sys
from datetime import UTC
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, TextIO

from loguru import logger

if TYPE_CHECKING:
    from loguru import Record

from route_agent.observability.context import current_context
from route_agent.observability.intercept import intercept_stdlib
from route_agent.paths import development_root, user_cache_root

LogFormat = Literal["text", "json"]

_HANDLER_IDS: list[int] = []
_SKIP_EXTRA = {
    "component",
    "event",
    "json",
    "serialized",
    "run_id",
    "request_id",
    "job_id",
    "source",
    "command",
    "stage",
    "duration_ms",
    "status",
}


def env_verbose() -> int:
    raw = os.environ.get("ROUTE_AGENT_VERBOSE")
    if raw is None or raw == "":
        return 0
    try:
        return max(0, int(raw))
    except ValueError:
        return 0


def env_log_format(*, default: LogFormat = "json") -> LogFormat:
    raw = os.environ.get("ROUTE_AGENT_LOG_FORMAT", default)
    if raw == "text":
        return "text"
    if raw == "json":
        return "json"
    return default


def log_level(*, verbose: int = 0, quiet: bool = False) -> str:
    if quiet:
        return "ERROR"
    if verbose >= 3:
        return "TRACE"
    if verbose >= 2:
        return "DEBUG"
    if verbose >= 1:
        return "INFO"
    return "WARNING"


def default_log_dir() -> Path | None:
    override = os.environ.get("ROUTE_AGENT_LOG_DIR")
    if override:
        return Path(override).expanduser()
    return None


def development_log_dir() -> Path:
    checkout = development_root()
    if checkout is not None:
        return checkout / ".observability" / "logs"
    return user_cache_root() / "logs"


def configure_logging(
    *,
    verbose: int = 0,
    quiet: bool = False,
    log_format: LogFormat = "text",
    stream: TextIO | None = None,
    log_dir: Path | None = None,
    enqueue: bool = True,
) -> None:
    """Replace Loguru handlers. Safe to call more than once."""
    global _HANDLER_IDS
    level = log_level(verbose=verbose, quiet=quiet)
    target = stream if stream is not None else sys.stderr
    resolved_dir = log_dir if log_dir is not None else default_log_dir()
    logger.remove()
    _HANDLER_IDS.clear()
    logger.configure(patcher=_patch_record)
    if log_format == "json":
        handler_id = logger.add(
            target,
            level=level,
            format=_json_format,
            colorize=False,
            backtrace=False,
            diagnose=False,
        )
    else:
        handler_id = logger.add(
            target,
            level=level,
            format=_text_format,
            colorize=False,
            backtrace=False,
            diagnose=False,
        )
    _HANDLER_IDS.append(handler_id)
    if resolved_dir is not None:
        resolved_dir.mkdir(parents=True, exist_ok=True)
        file_id = logger.add(
            str(resolved_dir / "route-agent.jsonl"),
            level=level,
            format=_json_format,
            colorize=False,
            serialize=False,
            rotation="20 MB",
            retention="7 days",
            enqueue=enqueue,
            catch=True,
            backtrace=False,
            diagnose=False,
        )
        _HANDLER_IDS.append(file_id)
    intercept_stdlib(level=_stdlib_level(level))


def _stdlib_level(level: str) -> int:
    mapping = {
        "TRACE": logging.DEBUG,
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
    }
    return mapping.get(level, logging.WARNING)


def _patch_record(record: Record) -> None:
    extra = record["extra"]
    context = current_context()
    extra.setdefault("component", extra.get("component") or record.get("name"))
    extra.setdefault("event", record["message"])
    extra.setdefault("run_id", context["run_id"])
    extra.setdefault("request_id", context["request_id"])
    extra.setdefault("job_id", context["job_id"])
    extra.setdefault("source", context["source"])
    extra.setdefault("command", context["command"])
    extra.setdefault("stage", extra.get("stage"))
    extra.setdefault("duration_ms", extra.get("duration_ms"))
    extra.setdefault("status", extra.get("status"))


def _json_format(record: Record) -> str:
    record["extra"]["json"] = format_json_record(record)
    return "{extra[json]}\n"


def _text_format(record: Record) -> str:
    extra = record["extra"]
    extras = " ".join(
        f"{key}={value}"
        for key, value in sorted(extra.items())
        if key not in _SKIP_EXTRA and value is not None
    )
    name = extra.get("component") or record["name"]
    line = f"{record['level'].name} {name} — {record['message']}"
    if extras:
        line = f"{line} {extras}"
    record["extra"]["json"] = line
    return "{extra[json]}\n{exception}"


def format_json_record(record: Record) -> str:
    import json

    extra = record["extra"]
    payload: dict[str, Any] = {
        "timestamp": record["time"].astimezone(UTC).isoformat(),
        "level": record["level"].name,
        "logger": extra.get("component") or record["name"],
        "message": record["message"],
        "event": extra.get("event") or record["message"],
        "component": extra.get("component") or record["name"],
        "source": extra.get("source"),
        "run_id": extra.get("run_id"),
        "request_id": extra.get("request_id"),
        "job_id": extra.get("job_id"),
        "stage": extra.get("stage"),
        "duration_ms": extra.get("duration_ms"),
        "status": extra.get("status"),
    }
    if extra.get("command"):
        payload["command"] = extra["command"]
    for key, value in extra.items():
        if key in payload or key in {"json", "serialized"}:
            continue
        payload[key] = value
    exception = record.get("exception")
    if exception:
        payload["exception"] = str(exception)
    return json.dumps(payload, sort_keys=True, default=str)
