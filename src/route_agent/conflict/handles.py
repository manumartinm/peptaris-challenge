"""Resolve pending protecting-group handles from the chosen process."""

from __future__ import annotations

from typing import Any

from route_agent.models.agent import AgentCandidate


def resolve_pending_handles(
    output: dict[str, Any], candidate: AgentCandidate
) -> dict[str, Any]:
    handle = handle_from_process(candidate.process)
    if handle is None:
        return output
    protected = dict(output.get("protected") or {})
    changed = False
    for token, group in protected.items():
        if group != "pending":
            continue
        if token == candidate.site or token in tokens_in_site(candidate.site):
            protected[token] = handle
            changed = True
    if not changed:
        return output
    updated = dict(output)
    updated["protected"] = protected
    return updated


def tokens_in_site(site: str) -> set[str]:
    return {
        token for token in site.replace(",", " ").replace("-", " ").split() if token
    }


def handle_from_process(process_id: str) -> str | None:
    lowered = process_id.lower()
    if "ivdde" in lowered or "iv-dde" in lowered:
        return "ivDde"
    if "mtt" in lowered:
        return "Mtt"
    if "alloc" in lowered:
        return "Alloc"
    if "acm" in lowered:
        return "Acm"
    if "dde" in lowered:
        return "Dde"
    return None
