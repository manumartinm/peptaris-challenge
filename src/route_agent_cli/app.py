"""Click composition for the public ``route-agent`` command.

This module only assembles the command tree. Pipeline construction lives in
``route_agent.composition.wiring``. stdout is the JSON result; stderr is logs
and ``--explain`` progress.
"""

from __future__ import annotations

import click

from route_agent.version import package_version
from route_agent_cli.commands.config import config_group
from route_agent_cli.commands.context import CliContext
from route_agent_cli.commands.debug import (
    agent_command,
    debug_group,
    eval_command,
    hidden_alias,
    post_graph_command,
    walk_command,
)
from route_agent_cli.commands.doctor import doctor_command
from route_agent_cli.commands.run import run_command
from route_agent_cli.commands.validate import validate_command

EPILOG = (
    "Stdout is the JSON result. Logs and --explain go to stderr.\n"
    "Exit codes: 0 ok, 1 input, 2 validation/agent fail, 3 infrastructure."
)


@click.group(
    context_settings={"help_option_names": ["-h", "--help"], "max_content_width": 88},
    no_args_is_help=True,
    epilog=EPILOG,
    help=(
        "Synthesizability checker for designed peptide analogs.\n\n"
        "Typical first use:\n\n"
        "\b\n"
        "  route-agent config set-api-key anthropic\n"
        "  route-agent doctor\n"
        "  route-agent run REQUEST.json --explain\n\n"
        "Use --no-model to skip live LLM calls. The verdict stays honest when "
        "the decision would have needed the model."
    ),
)
@click.version_option(package_version(), prog_name="route-agent")
@click.option("-v", "--verbose", count=True, help="Progress (-v) or diagnostics (-vv).")
@click.option("-q", "--quiet", is_flag=True, help="Only print errors on stderr.")
@click.option(
    "--log-format",
    type=click.Choice(["text", "json"]),
    default=None,
    help="stderr format for logs and doctor.",
)
@click.pass_context
def app(
    ctx: click.Context,
    verbose: int,
    quiet: bool,
    log_format: str | None,
) -> None:
    obj = ctx.ensure_object(CliContext)
    obj.merge(verbose=verbose, quiet=quiet, log_format=log_format)  # type: ignore[arg-type]


app.add_command(run_command)
app.add_command(validate_command)
app.add_command(config_group)
app.add_command(doctor_command)
app.add_command(debug_group)
app.add_command(hidden_alias(agent_command, "agent", "debug agent"))
app.add_command(hidden_alias(walk_command, "walk", "debug walk"))
app.add_command(hidden_alias(post_graph_command, "post-graph", "debug post-graph"))
app.add_command(hidden_alias(eval_command, "eval", "debug eval"))
