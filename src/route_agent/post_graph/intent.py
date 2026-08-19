from __future__ import annotations

from route_agent.models.agent import AgentFinding, AgentResult


def intent_findings(result: AgentResult) -> tuple[AgentFinding, ...]:
    return tuple(
        finding for finding in result.findings if finding.kind == "intent_not_achieved"
    )


def keep_intent_findings_only(result: AgentResult) -> AgentResult:
    kept = intent_findings(result)
    dropped = tuple(
        finding.kind
        for finding in result.findings
        if finding.kind != "intent_not_achieved"
    )
    unknowns = result.unknowns
    if dropped:
        unknowns = unknowns + (f"dropped_non_intent_findings:{','.join(dropped)}",)
    passed = result.passed
    if kept:
        passed = False
    elif passed is True:
        passed = True
    return result.model_copy(
        update={"findings": kept, "unknowns": unknowns, "passed": passed}
    )


def intent_rank(result: AgentResult | None) -> int:
    if result is None:
        return 2
    findings = intent_findings(result)
    if findings or result.passed is False:
        return 2
    if result.passed is True:
        return 0
    return 1
