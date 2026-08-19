"""CLI-only settings helpers. Environment-backed Settings stay in the core."""

from __future__ import annotations

from route_agent.settings import Settings


def settings_from_cli(
    *,
    no_model: bool = False,
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> Settings:
    """Build settings. Explicit CLI values beat environment defaults."""
    settings = Settings(no_model=no_model)
    updates: dict[str, object] = {}
    if model:
        updates["model"] = model
    if reasoning_effort:
        updates["reasoning_effort"] = reasoning_effort
    if not updates:
        return settings
    return settings.model_copy(update=updates)
