"""Technical commands hidden from the default help surface."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import click
from pydantic import ValidationError as PydanticValidationError

from route_agent.composition.wiring import (
    build_agent_runtime,
    build_conflict_walker,
    build_parser,
    build_post_graph_validator,
    build_route_pipeline,
    first_candidate_from_request,
    flush_tracers,
)
from route_agent.evaluation import DevEvaluator
from route_agent.models.agent import AgentObjective
from route_agent.observability import LogFormat, StructuredLogger
from route_agent.paths import schema_path, score_py_path
from route_agent_cli.commands.context import (
    CliContext,
    apply_globals,
    cli_command,
    with_globals,
    with_model_options,
)
from route_agent_cli.commands.errors import (
    CommandExit,
    exit_input,
    exit_ok,
    exit_validation,
    handle_unexpected_error,
)
from route_agent_cli.commands.io import (
    load_design_request,
    load_json_object,
    state_payload_from_object,
    write_or_echo_json,
)
from route_agent_cli.observer import build_observer
from route_agent_cli.settings import settings_from_cli


def warn_deprecated_alias(name: str, replacement: str) -> None:
    click.echo(
        f"warning: `{name}` is deprecated; use `{replacement}` instead.",
        err=True,
    )


@click.group("debug", help="Technical commands for agent, walk, post-graph, and eval.")
def debug_group() -> None:
    """Hidden-from-root technical surface. Prefer ``run`` and ``validate``."""


@debug_group.command("agent")
@click.pass_context
@with_globals
@with_model_options
@click.argument("request_path", type=click.Path(path_type=Path))
@click.option(
    "--objective",
    type=click.Choice(
        ["check_compatibility", "check_intent", "literature", "final_judge"]
    ),
    default="check_compatibility",
    show_default=True,
    help="Single agent objective. Never writes a route verdict.",
)
@click.option(
    "--state",
    "state_path",
    type=click.Path(path_type=Path),
    help="Optional State_0 / state payload JSON.",
)
@click.option(
    "--output", "-o", type=click.Path(path_type=Path), help="Write JSON here."
)
@click.option("--no-model", is_flag=True, help="Skip the live model call.")
@click.option("--explain", is_flag=True, help="Show progress on stderr.")
def agent_command(
    ctx: click.Context,
    request_path: Path,
    objective: AgentObjective,
    state_path: Path | None,
    output: Path | None,
    no_model: bool,
    explain: bool,
    model: str | None,
    reasoning_effort: str | None,
    verbose: int,
    quiet: bool,
    log_format: LogFormat | None,
) -> None:
    """Run one Agent objective. Never writes a route verdict."""
    apply_globals(ctx, verbose=verbose, quiet=quiet, log_format=log_format)
    with cli_command("debug agent"):
        _run_agent(
            ctx,
            request_path,
            objective=objective,
            state_path=state_path,
            output=output,
            no_model=no_model,
            explain=explain,
            model=model,
            reasoning_effort=reasoning_effort,
        )


@debug_group.command("walk")
@click.pass_context
@with_globals
@with_model_options
@click.argument("request_path", type=click.Path(path_type=Path))
@click.option(
    "--output", "-o", type=click.Path(path_type=Path), help="Write JSON here."
)
@click.option("--no-model", is_flag=True, help="Skip the live model call.")
@click.option("--explain", is_flag=True, help="Show tree expansion on stderr.")
def walk_command(
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
    """Validate State_0 then expand the conflict tree."""
    apply_globals(ctx, verbose=verbose, quiet=quiet, log_format=log_format)
    with cli_command("debug walk"):
        _run_walk(
            ctx,
            request_path,
            output=output,
            no_model=no_model,
            explain=explain,
            model=model,
            reasoning_effort=reasoning_effort,
        )


@debug_group.command("post-graph")
@click.pass_context
@with_globals
@with_model_options
@click.argument("request_path", type=click.Path(path_type=Path))
@click.option(
    "--output", "-o", type=click.Path(path_type=Path), help="Write JSON here."
)
@click.option("--no-model", is_flag=True, help="Skip the live model call.")
@click.option("--explain", is_flag=True, help="Show survivor checks on stderr.")
def post_graph_command(
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
    """Validate survivors and select a winner. Not the route verdict."""
    apply_globals(ctx, verbose=verbose, quiet=quiet, log_format=log_format)
    with cli_command("debug post-graph"):
        _run_post_graph(
            ctx,
            request_path,
            output=output,
            no_model=no_model,
            explain=explain,
            model=model,
            reasoning_effort=reasoning_effort,
        )


@debug_group.command("eval")
@click.pass_context
@with_globals
@with_model_options
@click.argument("requests_path", type=click.Path(path_type=Path))
@click.option(
    "--expected",
    type=click.Path(path_type=Path),
    default=None,
    help="Official expected key JSONL. Omit to launch only, without scoring.",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default=Path("actual.jsonl"),
    show_default=True,
    help="Write actual JSONL.",
)
@click.option(
    "--report",
    type=click.Path(path_type=Path),
    default=Path("EVAL_REPORT.md"),
    show_default=True,
    help="Write EVAL_REPORT.md.",
)
@click.option(
    "--trace-dir",
    type=click.Path(path_type=Path),
    default=Path("traces"),
    show_default=True,
)
@click.option("--no-model", is_flag=True, help="Skip live model calls.")
@click.option(
    "--strict", is_flag=True, help="Exit 2 on invalid schema or expected key."
)
def eval_command(
    ctx: click.Context,
    requests_path: Path,
    expected: Path | None,
    output: Path,
    report: Path,
    trace_dir: Path,
    no_model: bool,
    strict: bool,
    model: str | None,
    reasoning_effort: str | None,
    verbose: int,
    quiet: bool,
    log_format: LogFormat | None,
) -> None:
    """Run a JSONL set. Scores with the official scorer when --expected is set."""
    apply_globals(ctx, verbose=verbose, quiet=quiet, log_format=log_format)
    with cli_command("debug eval"):
        _run_eval(
            ctx,
            requests_path,
            expected=expected,
            output=output,
            report=report,
            trace_dir=trace_dir,
            no_model=no_model,
            strict=strict,
            model=model,
            reasoning_effort=reasoning_effort,
        )


def hidden_alias(command: click.Command, name: str, replacement: str) -> click.Command:
    """Register a deprecated root-level name that forwards to ``debug``."""
    alias = copy.copy(command)
    alias.name = name
    alias.hidden = True
    original = command.callback
    if original is None:
        raise ValueError(f"command {command.name} has no callback")

    def wrapped(*args: Any, **kwargs: Any) -> Any:
        warn_deprecated_alias(name, f"route-agent {replacement}")
        return original(*args, **kwargs)

    alias.callback = wrapped
    return alias


def _run_agent(
    ctx: click.Context,
    request_path: Path,
    *,
    objective: AgentObjective,
    state_path: Path | None,
    output: Path | None,
    no_model: bool,
    explain: bool,
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> None:
    cli: CliContext = ctx.ensure_object(CliContext)
    logger = StructuredLogger("route_agent.cli")
    observer = build_observer(explain=explain)
    try:
        request = load_design_request(request_path, logger, observer)
        state_payload: dict[str, Any] = {}
        if state_path is not None:
            loaded = load_json_object(state_path, logger, label="state")
            state_payload = state_payload_from_object(loaded)
        settings = settings_from_cli(
            no_model=no_model, model=model, reasoning_effort=reasoning_effort
        )
        runtime, families = build_agent_runtime(settings, logger=logger)
        try:
            candidate = first_candidate_from_request(request, families)
        except ValueError as exc:
            logger.error(str(exc))
            exit_input()
        result = runtime.invoke(objective, request, state_payload, candidate)
        write_or_echo_json(result.model_dump_json(indent=2), output)
        if result.passed is False:
            exit_validation()
        exit_ok()
    except CommandExit:
        raise
    except Exception as exc:  # noqa: BLE001
        handle_unexpected_error(exc, logger, verbose=cli.verbose)
    finally:
        observer.close()
        flush_tracers()


def _run_walk(
    ctx: click.Context,
    request_path: Path,
    *,
    output: Path | None,
    no_model: bool,
    explain: bool,
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> None:
    cli: CliContext = ctx.ensure_object(CliContext)
    logger = StructuredLogger("route_agent.cli")
    observer = build_observer(explain=explain)
    try:
        request = load_design_request(request_path, logger, observer)
        settings = settings_from_cli(
            no_model=no_model, model=model, reasoning_effort=reasoning_effort
        )
        validation = build_parser(
            settings, observer=observer, logger=logger
        ).run_validation_pipeline(request)
        walker, _runtime, _families = build_conflict_walker(
            settings, logger, observer=observer
        )
        tree = walker.walk(request, validation)
        report = tree.to_report(
            request.request_id, extra_calls=validation.state.llm_calls
        )
        logger.info(
            "conflict_walk_complete",
            request_id=request.request_id,
            nodes=len(report.nodes),
            surviving=len(report.surviving_ids),
            cost_usd=report.cost.total.cost_usd,
            calls=report.cost.total.calls,
        )
        write_or_echo_json(report.model_dump_json(indent=2), output)
        if validation.state.status == "fail" or not tree.surviving_ids:
            exit_validation()
        exit_ok()
    except CommandExit:
        raise
    except Exception as exc:  # noqa: BLE001
        handle_unexpected_error(exc, logger, verbose=cli.verbose)
    finally:
        observer.close()
        flush_tracers()


def _run_post_graph(
    ctx: click.Context,
    request_path: Path,
    *,
    output: Path | None,
    no_model: bool,
    explain: bool,
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> None:
    cli: CliContext = ctx.ensure_object(CliContext)
    logger = StructuredLogger("route_agent.cli")
    observer = build_observer(explain=explain)
    try:
        request = load_design_request(request_path, logger, observer)
        settings = settings_from_cli(
            no_model=no_model, model=model, reasoning_effort=reasoning_effort
        )
        validation = build_parser(
            settings, observer=observer, logger=logger
        ).run_validation_pipeline(request)
        walker, runtime, _families = build_conflict_walker(
            settings, logger, observer=observer
        )
        tree = walker.walk(request, validation)
        report = build_post_graph_validator(
            settings, runtime, logger, observer=observer
        ).validate(request, validation, tree)
        logger.info(
            "post_graph_cli_complete",
            request_id=request.request_id,
            selected_id=report.selected_id,
            surviving=len(report.surviving_ids),
            cost_usd=report.cost.total.cost_usd,
            calls=report.cost.total.calls,
        )
        write_or_echo_json(report.model_dump_json(indent=2), output)
        if validation.state.status == "fail" or report.selected_id is None:
            exit_validation()
        exit_ok()
    except CommandExit:
        raise
    except Exception as exc:  # noqa: BLE001
        handle_unexpected_error(exc, logger, verbose=cli.verbose)
    finally:
        observer.close()
        flush_tracers()


def _run_eval(
    ctx: click.Context,
    requests_path: Path,
    *,
    expected: Path | None,
    output: Path,
    report: Path,
    trace_dir: Path,
    no_model: bool,
    strict: bool,
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> None:
    cli: CliContext = ctx.ensure_object(CliContext)
    logger = StructuredLogger("route_agent.cli")
    try:
        if not requests_path.is_file():
            logger.error("requests file not found", path=str(requests_path))
            exit_input()
        if expected is not None and not expected.is_file():
            logger.error("expected file not found", path=str(expected))
            exit_input()
        settings = settings_from_cli(
            no_model=no_model, model=model, reasoning_effort=reasoning_effort
        )
        try:
            summary = DevEvaluator(
                build_route_pipeline(settings, logger, trace_dir),
                score_py=score_py_path(),
                schema_json=schema_path(),
                logger=logger,
            ).run(
                requests_path=requests_path,
                expected_path=expected,
                actual_path=output,
                report_path=report,
                trace_dir=trace_dir,
            )
        except (json.JSONDecodeError, PydanticValidationError) as exc:
            logger.error("invalid eval input", error=str(exc))
            exit_input()
        except ValueError as exc:
            logger.error("invalid eval input", error=str(exc))
            if "expected key" in str(exc):
                exit_validation()
            exit_input()
        if strict and (summary.schema.get("invalid") or summary.key_problems):
            exit_validation()
        exit_ok()
    except CommandExit:
        raise
    except Exception as exc:  # noqa: BLE001
        handle_unexpected_error(exc, logger, verbose=cli.verbose)
    finally:
        flush_tracers()
