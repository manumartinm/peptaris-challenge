"""Public ``route-agent validate`` command."""

from __future__ import annotations

from pathlib import Path

import click

from route_agent.composition.wiring import build_parser, flush_tracers
from route_agent.models.events import PipelineEvent
from route_agent.observability import LogFormat, bind_context
from route_agent_cli.commands.context import (
    apply_globals,
    cli_command,
    with_globals,
    with_model_options,
)
from route_agent_cli.commands.errors import (
    CommandExit,
    exit_ok,
    exit_validation,
    handle_unexpected_error,
)
from route_agent_cli.commands.io import load_design_request, write_or_echo_json
from route_agent_cli.observer import build_observer
from route_agent_cli.settings import settings_from_cli


@click.command(
    "validate",
    help="Run validation and emit State_0 JSON. Not the final route verdict.",
)
@click.pass_context
@with_globals
@with_model_options
@click.argument("request_path", type=click.Path(path_type=Path))
@click.option(
    "--output", "-o", type=click.Path(path_type=Path), help="Write JSON here."
)
@click.option("--no-model", is_flag=True, help="Skip the live model call.")
@click.option(
    "--explain",
    is_flag=True,
    help="Show validation stages on stderr. Does not change stdout JSON.",
)
def validate_command(
    ctx: click.Context,
    request_path: Path,
    output: Path | None,
    no_model: bool,
    explain: bool,
    model: str | None,
    reasoning_effort: str | None,
    verbose: int,
    quiet: bool,
    log_format: LogFormat | None,
) -> None:
    cli = apply_globals(ctx, verbose=verbose, quiet=quiet, log_format=log_format)
    observer = build_observer(explain=explain)
    with cli_command("validate") as logger:
        try:
            request = load_design_request(request_path, logger, observer)
            settings = settings_from_cli(
                no_model=no_model, model=model, reasoning_effort=reasoning_effort
            )
            with bind_context(request_id=request.request_id):
                logger.info("validating", request_id=request.request_id)
                result = build_parser(
                    settings, observer=observer, logger=logger
                ).run_validation_pipeline(request)
                observer.on_event(
                    PipelineEvent(
                        kind="stage_finished",
                        stage="validating",
                        request_id=request.request_id,
                        status=result.state.status,
                    )
                )
                logger.info("writing result", request_id=request.request_id)
                write_or_echo_json(result.model_dump_json(indent=2), output)
                if result.state.status == "fail":
                    exit_validation()
                exit_ok()
        except CommandExit:
            raise
        except Exception as exc:  # noqa: BLE001
            handle_unexpected_error(exc, logger, verbose=cli.verbose)
        finally:
            observer.close()
            flush_tracers()
