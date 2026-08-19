from __future__ import annotations

from typing import Any

from route_agent.models.agent import AgentResult
from route_agent.models.conflict import ConflictTree, ValidationResult
from route_agent.models.molecular import PostGraphValidationReport
from route_agent.models.verdict import Confidence, RouteVerdict
from route_agent.verdict.conflicts import consolidate_conflicts
from route_agent.verdict.kinds import SCHEMA_KINDS
from route_agent.verdict.ladder import compute_verdict
from route_agent.verdict.route import reconstruct_route

MODEL_DISABLED_UNKNOWN = (
    "model disabled: compatibility, intent, and final_judge were not run"
)


class RouteAssembler:
    def assemble(
        self,
        *,
        request_id: str,
        validation: ValidationResult,
        tree: ConflictTree,
        post_graph: PostGraphValidationReport,
        families: Any,
        judge: AgentResult | None,
    ) -> RouteVerdict:
        route = reconstruct_route(tree, post_graph.selected_id, families)
        conflicts = consolidate_conflicts(
            validation, tree, post_graph.selected_id, post_graph
        )
        verdict = compute_verdict(validation, tree, post_graph, conflicts)
        confidence = self._confidence(judge)
        unknowns = self._unknowns(validation, post_graph, judge, tree)
        return RouteVerdict(
            request_id=request_id,
            verdict=verdict,
            confidence=confidence,
            resolved_sequence=validation.resolved_sequence,
            resolved_annotations=dict(validation.resolved_annotations),
            site_map=validation.site_map,
            route=route,
            conflicts=conflicts,
            unknowns=unknowns,
        )

    def _confidence(self, judge: AgentResult | None) -> Confidence:
        if judge is None or judge.confidence is None:
            return "low"
        return judge.confidence

    def _unknowns(
        self,
        validation: ValidationResult,
        post_graph: PostGraphValidationReport,
        judge: AgentResult | None,
        tree: ConflictTree | None = None,
    ) -> tuple[str, ...]:
        items: list[str] = list(validation.unknowns)
        items.extend(post_graph.unknowns)
        if judge is not None:
            items.extend(judge.unknowns)
            items.extend(judge.gaps)
        items.extend(_unread_conflict_kinds(tree, post_graph, judge))
        unique: list[str] = []
        seen: set[str] = set()
        for item in items:
            rewritten = MODEL_DISABLED_UNKNOWN if item == "model disabled" else item
            if rewritten in seen:
                continue
            seen.add(rewritten)
            unique.append(rewritten)
        return tuple(unique)


def _unread_conflict_kinds(
    tree: ConflictTree | None,
    post_graph: PostGraphValidationReport,
    judge: AgentResult | None,
) -> tuple[str, ...]:
    kinds: list[str] = []
    results: list[AgentResult] = []
    if judge is not None:
        results.append(judge)
    if tree is not None and post_graph.selected_id is not None:
        result = tree.node(post_graph.selected_id).agent_result
        if result is not None:
            results.append(result)
    for item in post_graph.candidates:
        if item.intent is not None:
            results.append(item.intent)
    for result in results:
        for finding in result.findings:
            if finding.kind not in SCHEMA_KINDS:
                kinds.append(f"unreadable_conflict_kind:{finding.kind}")
    return tuple(kinds)


def assemble_route_verdict(
    *,
    request_id: str,
    validation: ValidationResult,
    tree: ConflictTree,
    post_graph: PostGraphValidationReport,
    families: Any,
    judge: AgentResult | None,
) -> RouteVerdict:
    return RouteAssembler().assemble(
        request_id=request_id,
        validation=validation,
        tree=tree,
        post_graph=post_graph,
        families=families,
        judge=judge,
    )
