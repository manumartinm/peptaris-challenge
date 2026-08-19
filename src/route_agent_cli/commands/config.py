"""Store and inspect provider credentials without printing secrets."""

from __future__ import annotations

import getpass

import click

from route_agent.credentials import (
    PROVIDERS,
    CredentialError,
    credential_status,
    set_api_key,
    unset_api_key,
)
from route_agent.observability import LogFormat
from route_agent.settings import Settings
from route_agent_cli.commands.context import (
    EXIT_INPUT,
    apply_globals,
    cli_command,
    with_globals,
)
from route_agent_cli.commands.errors import CommandExit, handle_unexpected_error


@click.group("config", help="Store API keys in the system keyring and inspect config.")
def config_group() -> None:
    """Manage credentials. Values are never printed."""


@config_group.command("set-api-key")
@click.pass_context
@with_globals
@click.argument("provider", type=click.Choice(PROVIDERS))
@click.option(
    "--key",
    default=None,
    help="Avoid this flag; prefer the hidden prompt so the key stays out of history.",
)
def set_api_key_command(
    ctx: click.Context,
    provider: str,
    key: str | None,
    verbose: int,
    quiet: bool,
    log_format: LogFormat | None,
) -> None:
    """Save an OpenAI or Anthropic key in the system keyring."""
    cli = apply_globals(ctx, verbose=verbose, quiet=quiet, log_format=log_format)
    with cli_command("config set-api-key") as logger:
        try:
            secret = key if key else getpass.getpass(f"{provider} API key: ")
            set_api_key(provider, secret)
            click.echo(f"stored {provider} API key in the system keyring", err=True)
        except (ValueError, CredentialError) as exc:
            logger.error(
                str(exc), hint="set OPENAI_API_KEY or ANTHROPIC_API_KEY instead"
            )
            raise CommandExit(EXIT_INPUT) from exc
        except Exception as exc:  # noqa: BLE001
            handle_unexpected_error(exc, logger, verbose=cli.verbose)


@config_group.command("unset-api-key")
@click.pass_context
@with_globals
@click.argument("provider", type=click.Choice(PROVIDERS))
def unset_api_key_command(
    ctx: click.Context,
    provider: str,
    verbose: int,
    quiet: bool,
    log_format: LogFormat | None,
) -> None:
    """Remove a stored key from the system keyring."""
    cli = apply_globals(ctx, verbose=verbose, quiet=quiet, log_format=log_format)
    with cli_command("config unset-api-key") as logger:
        try:
            removed = unset_api_key(provider)
            if removed:
                click.echo(f"removed {provider} API key from the keyring", err=True)
            else:
                click.echo(f"no {provider} API key was stored", err=True)
        except CredentialError as exc:
            logger.error(str(exc))
            raise CommandExit(EXIT_INPUT) from exc
        except Exception as exc:  # noqa: BLE001
            handle_unexpected_error(exc, logger, verbose=cli.verbose)


@config_group.command("show")
@click.pass_context
@with_globals
def show_command(
    ctx: click.Context,
    verbose: int,
    quiet: bool,
    log_format: LogFormat | None,
) -> None:
    """Show model and whether keys exist. Never prints secret values."""
    cli = apply_globals(ctx, verbose=verbose, quiet=quiet, log_format=log_format)
    with cli_command("config show") as logger:
        try:
            settings = Settings()
            click.echo(f"model: {settings.model}")
            click.echo(f"provider: {settings.model_provider()}")
            click.echo(f"no_model: {settings.no_model}")
            for name in PROVIDERS:
                env_value = (
                    settings.secret_value_or_none(settings.openai_api_key)
                    if name == "openai"
                    else settings.secret_value_or_none(settings.anthropic_api_key)
                )
                status = credential_status(name, env_value=env_value)
                source = status.source or "absent"
                click.echo(f"{name} key: {source}")
            langfuse = bool(
                settings.secret_value_or_none(settings.langfuse_public_key)
                and settings.secret_value_or_none(settings.langfuse_secret_key)
            )
            click.echo(f"langfuse: {'configured' if langfuse else 'absent'}")
        except Exception as exc:  # noqa: BLE001
            handle_unexpected_error(exc, logger, verbose=cli.verbose)
