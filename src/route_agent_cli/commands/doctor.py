"""Public ``route-agent doctor`` command."""

from __future__ import annotations

import json

import click

from route_agent.doctor import DoctorCheck, run_doctor
from route_agent.observability import LogFormat
from route_agent.settings import Settings
from route_agent_cli.commands.context import (
    EXIT_INFRA,
    apply_globals,
    cli_command,
    with_globals,
)
from route_agent_cli.commands.errors import CommandExit, handle_unexpected_error


@click.command(
    "doctor",
    help="Check Python, packaged resources, RDKit, API keys, and writable dirs.",
)
@click.pass_context
@with_globals
@click.option("--no-model", is_flag=True, help="Treat a missing API key as a warning.")
def doctor_command(
    ctx: click.Context,
    no_model: bool,
    verbose: int,
    quiet: bool,
    log_format: LogFormat | None,
) -> None:
    cli = apply_globals(ctx, verbose=verbose, quiet=quiet, log_format=log_format)
    with cli_command("doctor") as logger:
        try:
            settings = Settings(no_model=no_model)
            report = run_doctor(settings, no_model=no_model)
            if cli.log_format == "json":
                click.echo(json.dumps(report.as_payload(), indent=2, sort_keys=True))
            else:
                _print_table(report.checks)
            if report.failed:
                raise CommandExit(EXIT_INFRA)
        except CommandExit:
            raise
        except Exception as exc:  # noqa: BLE001
            handle_unexpected_error(exc, logger, verbose=cli.verbose)


def _print_table(checks: tuple[DoctorCheck, ...]) -> None:
    name_width = max(len(item.name) for item in checks)
    status_width = max(len(item.status) for item in checks)
    for item in checks:
        click.echo(
            f"{item.name:<{name_width}}  {item.status:<{status_width}}  {item.detail}"
        )
