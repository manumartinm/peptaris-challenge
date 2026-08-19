"""Application logger: Loguru with structured extras and secret redaction."""

from __future__ import annotations

from typing import Any

from loguru import logger

from route_agent.observability.intercept import InterceptHandler
from route_agent.observability.redaction import redact_fields


class StructuredLogger:
    """Loguru-backed structured logger. Extra kwargs become JSON fields."""

    def __init__(self, name: str = "route_agent.validation") -> None:
        self.name = name
        self._bound = logger.bind(component=name)

    def bind(self, **fields: Any) -> StructuredLogger:
        child = StructuredLogger(self.name)
        child._bound = self._bound.bind(**redact_fields(fields))
        return child

    def trace(self, message: str, **fields: Any) -> None:
        self._log("TRACE", message, **fields)

    def debug(self, message: str, **fields: Any) -> None:
        self._log("DEBUG", message, **fields)

    def info(self, message: str, **fields: Any) -> None:
        self._log("INFO", message, **fields)

    def warning(self, message: str, **fields: Any) -> None:
        self._log("WARNING", message, **fields)

    def error(self, message: str, **fields: Any) -> None:
        self._log("ERROR", message, **fields)

    def _log(self, level: str, message: str, **fields: Any) -> None:
        extra = redact_fields(fields)
        extra.setdefault("event", message)
        self._bound.bind(**extra).opt(depth=1).log(level, message)
        self._echo_stdlib(level, message, extra)

    def exception(self, message: str, **fields: Any) -> None:
        extra = redact_fields(fields)
        extra.setdefault("event", message)
        self._bound.bind(**extra).opt(depth=1, exception=True).error(message)
        self._echo_stdlib("ERROR", message, extra, exc_info=True)

    def _echo_stdlib(
        self,
        level: str,
        message: str,
        extra: dict[str, Any],
        *,
        exc_info: bool = False,
    ) -> None:
        import logging

        root = logging.getLogger()
        std = logging.getLogger(self.name)
        handlers = (*std.handlers, *root.handlers)
        if not handlers:
            return
        if all(isinstance(handler, InterceptHandler) for handler in handlers):
            return
        if level == "TRACE":
            numeric = logging.DEBUG
        else:
            numeric = getattr(logging, level, logging.INFO)
        logging.getLogger(self.name).log(
            numeric,
            message,
            extra={"structured_fields": extra},
            exc_info=exc_info,
        )
