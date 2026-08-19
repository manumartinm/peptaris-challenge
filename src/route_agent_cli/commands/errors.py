"""Typed command failures mapped to the public exit-code table."""

from __future__ import annotations

from typing import Any, NoReturn

import click

from route_agent.observability import StructuredLogger
from route_agent_cli.commands.context import EXIT_INFRA, EXIT_INPUT, EXIT_VALIDATION


class CommandExit(click.exceptions.Exit):
    """Stop a command with a documented exit code."""


def exit_input() -> NoReturn:
    raise CommandExit(EXIT_INPUT)


def exit_validation() -> NoReturn:
    raise CommandExit(EXIT_VALIDATION)


def exit_ok() -> NoReturn:
    raise CommandExit(0)


def handle_unexpected_error(
    exc: Exception,
    logger: StructuredLogger,
    *,
    verbose: int,
) -> NoReturn:
    """Log an infrastructure failure. Tracebacks only appear at ``-vv``."""
    hint = (
        f"{type(exc).__name__}: {exc}. "
        "Re-run with -vv for a traceback, or `route-agent doctor` to check setup."
    )
    if verbose >= 2:
        logger.exception("infrastructure failure", error_type=type(exc).__name__)
    else:
        logger.error(
            "infrastructure failure",
            error_type=type(exc).__name__,
            error=str(exc),
            hint=hint,
        )
    raise CommandExit(EXIT_INFRA) from exc


def format_input_error(message: str, **fields: Any) -> dict[str, Any]:
    return {"error": message, **fields}
