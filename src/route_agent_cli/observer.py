"""CLI explain observer. Presentation only; the core never imports this."""

from __future__ import annotations

from route_agent.observe import NoOpObserver, PipelineObserver
from route_agent_cli.explain import build_explain_observer


def build_observer(
    *, explain: bool, interactive: bool | None = None
) -> PipelineObserver:
    if not explain:
        return NoOpObserver()
    return build_explain_observer(interactive=interactive)
