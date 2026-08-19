from __future__ import annotations

from route_agent.models.agent import AgentResult, CostReport, LLMCall
from route_agent.models.conflict import ConflictTreeReport, ValidationResult
from route_agent.models.events import PipelineEvent
from route_agent.models.frozen import FrozenModel
from route_agent.models.molecular import PostGraphValidationReport
from route_agent.models.request import DesignRequest
from route_agent.models.verdict import RouteVerdict


class PipelineTrace(FrozenModel):
    request_id: str
    run_id: str | None = None
    job_id: str | None = None
    request: DesignRequest
    validation: ValidationResult
    tree: ConflictTreeReport
    post_graph: PostGraphValidationReport
    judge: AgentResult | None
    verdict: RouteVerdict
    cost: CostReport
    llm_calls: tuple[LLMCall, ...] = ()
    events: tuple[PipelineEvent, ...] = ()
    trace_version: int = 3
