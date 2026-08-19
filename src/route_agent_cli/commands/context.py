"""Shared CLI context, exit codes, and global option wiring."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from time import perf_counter
from typing import Any

import click
from loguru import logger as loguru_logger

from route_agent.observability import (
    LogFormat,
    StructuredLogger,
    bind_context,
    configure_logging,
    default_log_dir,
    env_verbose,
    new_run_id,
)

EXIT_OK = 0
EXIT_INPUT = 1
EXIT_VALIDATION = 2
EXIT_INFRA = 3


@dataclass
class CliContext:
    """Options shared by every command. Stored on ``click.Context.obj``."""

    verbose: int = 0
    quiet: bool = False
    log_format: LogFormat = "text"

    def merge(
        self,
        *,
        verbose: int = 0,
        quiet: bool = False,
        log_format: LogFormat | None = None,
    ) -> None:
        self.verbose = max(self.verbose, verbose, env_verbose())
        self.quiet = self.quiet or quiet
        if log_format is not None:
            self.log_format = log_format
        configure_logging(
            verbose=self.verbose,
            quiet=self.quiet,
            log_format=self.log_format,
            log_dir=default_log_dir(),
            enqueue=False,
        )


def apply_globals(
    ctx: click.Context,
    *,
    verbose: int = 0,
    quiet: bool = False,
    log_format: LogFormat | None = None,
) -> CliContext:
    obj = ctx.ensure_object(CliContext)
    obj.merge(verbose=verbose, quiet=quiet, log_format=log_format)
    return obj


def with_globals[F: Callable[..., Any]](command: F) -> F:
    """Attach ``-v/-q/--log-format`` to a command without replacing its signature.

    Place this below ``@click.command()``. The callback must accept
    ``verbose``, ``quiet``, and ``log_format`` and call ``apply_globals``.
    """
    decorated = click.option(
        "--log-format",
        type=click.Choice(["text", "json"]),
        default=None,
        help="stderr format. JSON keeps timestamps and request ids.",
    )(command)
    decorated = click.option(
        "-q",
        "--quiet",
        is_flag=True,
        help="Only print errors on stderr.",
    )(decorated)
    decorated = click.option(
        "-v",
        "--verbose",
        count=True,
        help="Show progress (-v) or diagnostic detail (-vv).",
    )(decorated)
    return decorated


REASONING_EFFORTS = ("none", "low", "medium", "high")


def with_model_options[F: Callable[..., Any]](command: F) -> F:
    """Attach ``--model`` and ``--reasoning`` below ``@click.command()``."""
    decorated = click.option(
        "--reasoning",
        "reasoning_effort",
        type=click.Choice(REASONING_EFFORTS, case_sensitive=False),
        default=None,
        help="Reasoning effort for GPT-5-class models. Overrides the env default.",
    )(command)
    decorated = click.option(
        "--model",
        default=None,
        help="LiteLLM model, e.g. openai/gpt-5.6-terra. Overrides ROUTE_AGENT_MODEL.",
    )(decorated)
    return decorated


@contextmanager
def cli_command(name: str) -> Iterator[StructuredLogger]:
    logger = StructuredLogger("route_agent.cli")
    started = perf_counter()
    exit_code = EXIT_OK
    with bind_context(run_id=new_run_id(), source="cli", command=name):
        logger.info("command_start", command=name)
        try:
            yield logger
        except click.exceptions.Exit as exc:
            exit_code = exc.exit_code
            raise
        except Exception:
            exit_code = EXIT_INFRA
            raise
        finally:
            logger.info(
                "command_finish",
                command=name,
                duration_ms=round((perf_counter() - started) * 1000, 3),
                exit_code=exit_code,
                status="ok" if exit_code == EXIT_OK else "error",
            )
            loguru_logger.complete()
