"""Collect LLMCall records from the public pipeline artifacts."""

from __future__ import annotations

from route_agent.models.agent import AgentResult, LLMCall
from route_agent.models.conflict import ConflictTree, ValidationResult
from route_agent.models.molecular import PostGraphValidationReport


def collect_llm_calls(
    validation: ValidationResult,
    tree: ConflictTree,
    post_graph: PostGraphValidationReport | None = None,
    judge: AgentResult | None = None,
) -> list[LLMCall]:
    calls = list(validation.state.llm_calls)
    for node_id in tree.graph.nodes:
        calls.extend(tree.node(node_id).state.llm_calls)
    if post_graph is not None:
        for item in post_graph.candidates:
            if item.intent is not None and item.intent.llm_call is not None:
                calls.append(item.intent.llm_call)
    if judge is not None and judge.llm_call is not None:
        calls.append(judge.llm_call)
    return calls
