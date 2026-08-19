"""Shared markers for timeouts and agent invocation failures."""

from __future__ import annotations

from route_agent.models.agent import AgentResult

INFRA_UNKNOWNS = {"check_timeout", "unreadable_agent_output"}


def is_infrastructure_unknown(result: AgentResult) -> bool:
    for item in result.unknowns:
        if item in INFRA_UNKNOWNS:
            return True
        if item.startswith("agent_invoke_failed:"):
            return True
    return False
