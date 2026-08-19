from __future__ import annotations

from route_agent.agent.failures import is_infrastructure_unknown
from route_agent.models.conflict import ConflictTree, ValidationResult
from route_agent.models.molecular import PostGraphValidationReport
from route_agent.models.verdict import RouteConflict, Verdict
from route_agent.verdict.path import path_nodes

REFUSALS = {"infeasible", "insufficient_information"}


class VerdictLadder:
    def compute(
        self,
        validation: ValidationResult,
        tree: ConflictTree,
        post_graph: PostGraphValidationReport,
        conflicts: tuple[RouteConflict, ...],
    ) -> Verdict:
        blocking = any(item.severity == "blocking" for item in conflicts)
        major = any(item.severity == "major" for item in conflicts)
        insufficient = self._information_is_insufficient(
            validation, tree, post_graph, conflicts
        )
        if insufficient:
            chosen: Verdict = "insufficient_information"
        elif blocking or (
            post_graph.selected_id is None and self._explicit_chemistry_failure(tree)
        ):
            chosen = "infeasible"
        elif post_graph.selected_id is None:
            chosen = "insufficient_information"
        elif major:
            chosen = "feasible_with_changes"
        else:
            chosen = "feasible"
        if chosen == "feasible" and (blocking or major):
            chosen = "infeasible" if blocking else "feasible_with_changes"
        if blocking and chosen not in REFUSALS:
            chosen = "infeasible"
        return chosen

    def _information_is_insufficient(
        self,
        validation: ValidationResult,
        tree: ConflictTree,
        post_graph: PostGraphValidationReport,
        conflicts: tuple[RouteConflict, ...],
    ) -> bool:
        if any(item.kind == "site_invalid" for item in conflicts):
            return False
        markers = (
            *validation.unknowns,
            *post_graph.unknowns,
        )
        if any("model disabled" in item for item in markers):
            return True
        if self._blocking_is_only_missing_building_blocks(conflicts):
            return True
        for node in path_nodes(tree, post_graph.selected_id):
            result = node.agent_result
            if result is None:
                continue
            if any(
                item == "model disabled" or item.startswith("check_timeout")
                for item in result.unknowns
            ):
                return True
        return False

    def _blocking_is_only_missing_building_blocks(
        self, conflicts: tuple[RouteConflict, ...]
    ) -> bool:
        blocking = [item for item in conflicts if item.severity == "blocking"]
        return bool(blocking) and all(
            item.kind == "building_block_availability" for item in blocking
        )

    def _explicit_chemistry_failure(self, tree: ConflictTree) -> bool:
        failed = False
        for node_id in tree.graph.nodes:
            node = tree.node(node_id)
            if node.agent_result is None:
                continue
            if is_infrastructure_unknown(node.agent_result):
                continue
            if node.agent_result.passed is False:
                failed = True
            if node.agent_result.passed is None:
                return False
        return failed


def compute_verdict(
    validation: ValidationResult,
    tree: ConflictTree,
    post_graph: PostGraphValidationReport,
    conflicts: tuple[RouteConflict, ...],
) -> Verdict:
    return VerdictLadder().compute(validation, tree, post_graph, conflicts)
