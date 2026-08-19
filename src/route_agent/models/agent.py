from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from pydantic import Field

from route_agent.models.frozen import FrozenModel

LLMObjective = Literal[
    "structure_request",
    "check_compatibility",
    "check_intent",
    "final_judge",
]
LLMStage = Literal["validate", "walk", "post_graph"]


class ToolCall(FrozenModel):
    tool: str
    args: dict[str, Any]
    result_snippet: str
    truncated: bool


class LLMCall(FrozenModel):
    call_id: str
    model: str
    objective: LLMObjective
    input_tokens: int
    output_tokens: int
    cost_usd: float
    cache: dict[str, object]
    tool_calls: tuple[ToolCall, ...] = ()
    stage: LLMStage | None = None

    def resolved_stage(self) -> LLMStage:
        if self.stage is not None:
            return self.stage
        if self.objective == "structure_request":
            return "validate"
        if self.objective in {"check_intent", "final_judge"}:
            return "post_graph"
        return "walk"


class CostBreakdown(FrozenModel):
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0


class CostReport(FrozenModel):
    phases: dict[str, CostBreakdown] = Field(default_factory=dict)
    objectives: dict[str, CostBreakdown] = Field(default_factory=dict)
    total: CostBreakdown = Field(default_factory=CostBreakdown)


def build_cost_report(calls: Sequence[LLMCall]) -> CostReport:
    phases: dict[str, list[LLMCall]] = {
        "validate": [],
        "walk": [],
        "post_graph": [],
    }
    objectives: dict[str, list[LLMCall]] = {}
    for call in calls:
        phases[call.resolved_stage()].append(call)
        objectives.setdefault(call.objective, []).append(call)
    return CostReport(
        phases={name: _cost_breakdown(group) for name, group in phases.items()},
        objectives={name: _cost_breakdown(group) for name, group in objectives.items()},
        total=_cost_breakdown(calls),
    )


def _cost_breakdown(calls: Sequence[LLMCall]) -> CostBreakdown:
    return CostBreakdown(
        cost_usd=round(sum(call.cost_usd for call in calls), 8),
        input_tokens=sum(call.input_tokens for call in calls),
        output_tokens=sum(call.output_tokens for call in calls),
        calls=len(calls),
    )


class AgentCandidate(FrozenModel):
    family: str
    site: str
    process: str


from route_agent.models.corpus import Provenance  # noqa: E402

AgentObjective = Literal["check_compatibility", "check_intent", "final_judge"]
AgentConfidence = Literal["high", "medium", "low"]
AgentFindingKind = Literal[
    "protecting_group_orthogonality",
    "order_of_operations",
    "mutually_exclusive",
    "site_invalid",
    "reagent_incompatibility",
    "building_block_availability",
    "intent_not_achieved",
]


class AgentFinding(FrozenModel):
    kind: AgentFindingKind | str
    description: str
    affected: tuple[str, ...] = ()


class AgentResult(FrozenModel):
    objective: AgentObjective | None = None
    passed: bool | None = None
    resolution: str | None = None
    findings: tuple[AgentFinding, ...] = ()
    gaps: tuple[str, ...] = ()
    confidence: AgentConfidence | None = None
    citations: tuple[Provenance, ...] = ()
    unknowns: tuple[str, ...] = ()
    llm_call: LLMCall | None = None


class CitedFact(FrozenModel):
    text: str
    ref_row: int | None = None
    ref: str | None = None


class ProcessProfile(FrozenModel):
    family: str
    process_id: str
    found: bool
    name: str | None = None
    summary: str = ""
    requires: tuple[str, ...] = ()
    reagents: tuple[CitedFact, ...] = ()
    conditions: tuple[CitedFact, ...] = ()
    constraints: tuple[CitedFact, ...] = ()
    explicit_risks: tuple[CitedFact, ...] = ()
    explicit_alternatives: tuple[CitedFact, ...] = ()
    stage_hint: str | None = None
    building_blocks: tuple[str, ...] = ()
