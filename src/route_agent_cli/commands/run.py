"""Public ``route-agent run`` command."""

from __future__ import annotations

from pathlib import Path

import click

from route_agent.composition.wiring import build_route_pipeline, flush_tracers
from route_agent.models.events import PipelineEvent
from route_agent.observability import LogFormat, bind_context
from route_agent_cli.commands.context import (
    apply_globals,
    cli_command,
    with_globals,
    with_model_options,
)
from route_agent_cli.commands.errors import CommandExit, handle_unexpected_error
from route_agent_cli.commands.io import load_design_request, write_or_echo_json
from route_agent_cli.observer import build_observer
from route_agent_cli.settings import settings_from_cli


@click.command(
    "run",
    help="Validate, walk, judge, and emit one schema-exact RouteVerdict JSON.",
)
@click.pass_context
@with_globals
@with_model_options
@click.argument("request_path", type=click.Path(path_type=Path))
@click.option(
    "--output", "-o", type=click.Path(path_type=Path), help="Write JSON here."
)
@click.option(
    "--trace-dir",
    type=click.Path(path_type=Path),
    default=Path("traces"),
    show_default=True,
    help="Internal pipeline traces (not the public verdict).",
)
@click.option(
    "--no-model", is_flag=True, help="Skip live model calls; verdicts stay honest."
)
@click.option(
    "--explain",
    is_flag=True,
    help="Show stages, nodes, and diffs on stderr. Does not change stdout JSON.",
)
def run_command(
    ctx: click.Context,
    request_path: Path,
    output: Path | None,
    trace_dir: Path,
    no_model: bool,
    explain: bool,
    model: str | None,
    reasoning_effort: str | None,
    verbose: int,
    quiet: bool,
    log_format: LogFormat | None,
) -> None:
    """Emit a RouteVerdict. Always exits 0 when a schema object can be written."""
    cli = apply_globals(ctx, verbose=verbose, quiet=quiet, log_format=log_format)
    observer = build_observer(explain=explain)
    with cli_command("run") as logger:
        try:
            request = load_design_request(request_path, logger, observer)
            settings = settings_from_cli(
                no_model=no_model, model=model, reasoning_effort=reasoning_effort
            )
            with bind_context(request_id=request.request_id):
                logger.info(
                    "checking routes",
                    request_id=request.request_id,
                    model=settings.model,
                    reasoning_effort=settings.reasoning_effort,
                )
                result = build_route_pipeline(
                    settings, logger, trace_dir, observer=observer
                ).run(request)
                logger.info("writing result", request_id=request.request_id)
                observer.on_event(
                    PipelineEvent(
                        kind="verdict_ready",
                        stage="writing",
                        request_id=request.request_id,
                        message=result.verdict.verdict,
                        calls=result.cost.total.calls,
                        cost_usd=result.cost.total.cost_usd,
                    )
                )
                write_or_echo_json(result.verdict.model_dump_json(indent=2), output)
        except CommandExit:
            raise
        except Exception as exc:  # noqa: BLE001
            handle_unexpected_error(exc, logger, verbose=cli.verbose)
        finally:
            observer.close()
            flush_tracers()
