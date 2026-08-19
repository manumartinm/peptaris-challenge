from __future__ import annotations

from route_agent.models.agent import AgentFinding, AgentResult
from route_agent.models.conflict import ConflictTree, ValidationResult
from route_agent.models.corpus import Provenance, inference_provenance
from route_agent.models.molecular import PostGraphValidationReport
from route_agent.models.verdict import (
    ConflictSeverity,
    RouteConflict,
    SchemaConflictKind,
)
from route_agent.verdict.kinds import (
    CATALYST_KINDS,
    ON_RESIN_FAMILIES,
    cli_kind_from_agent,
    collect_unmapped_markers,
    has_head_to_tail_amide_clash,
    path_catalyst_conflict_kind,
    path_has_kinds,
    schema_kind,
    unmapped_families,
)
from route_agent.verdict.path import collect_winning_path

MISSING_HANDLE_MARKERS = ("acm", "no orthogonal", "building block", "unavailable")


class ConflictConsolidator:
    def consolidate(
        self,
        validation: ValidationResult,
        tree: ConflictTree,
        selected_id: str | None,
        post_graph: PostGraphValidationReport,
    ) -> tuple[RouteConflict, ...]:
        conflicts: list[RouteConflict] = [
            RouteConflict(
                severity=item.severity,
                kind=item.kind,
                description=item.description,
                affected=item.affected,
                resolution=item.resolution,
                provenance=item.provenance,
            )
            for item in validation.conflicts
        ]
        conflicts.extend(self._validation_gaps(validation, selected_id))
        conflicts.extend(
            self._unmapped_product_conflicts(validation, tree, selected_id, post_graph)
        )
        conflicts.extend(self._branch_conflicts(validation, tree, selected_id))
        conflicts.extend(
            self._winner_findings(validation, tree, selected_id, post_graph)
        )
        conflicts.extend(self._path_catalyst_conflicts(tree, selected_id))
        conflicts.extend(self._terminus_chemistry_conflicts(validation))
        return tuple(conflicts)

    def _branch_conflicts(
        self,
        validation: ValidationResult,
        tree: ConflictTree,
        selected_id: str | None,
    ) -> list[RouteConflict]:
        if selected_id is None:
            return self._dead_end_conflicts(validation, tree)
        path = collect_winning_path(tree, selected_id)
        emitted: list[RouteConflict] = []
        for parent_id, child_id in zip(path, path[1:], strict=False):
            winner = tree.node(child_id)
            if winner.candidate is None:
                continue
            siblings = [
                tree.node(node_id) for node_id in tree.graph.successors(parent_id)
            ]
            first = self._first_process(validation, winner.state.modification_ref)
            if first is None or winner.candidate.process == first:
                continue
            failed = next(
                (
                    sibling
                    for sibling in siblings
                    if sibling.candidate is not None
                    and sibling.candidate.process == first
                ),
                None,
            )
            finding = self._primary_finding(failed.agent_result if failed else None)
            kind = (
                cli_kind_from_agent(finding.kind, validation)
                if finding is not None
                else "protecting_group_orthogonality"
            )
            if kind is None:
                kind = "protecting_group_orthogonality"
            emitted.append(
                RouteConflict(
                    severity="major",
                    kind=kind,
                    description=(
                        finding.description
                        if finding
                        else (
                            f"{first} did not survive; "
                            f"continued with {winner.candidate.process}"
                        )
                    ),
                    affected=finding.affected if finding else (winner.candidate.site,),
                    resolution=winner.candidate.process,
                    provenance=self._finding_provenance(failed, winner),
                )
            )
        return emitted

    def _dead_end_conflicts(
        self, validation: ValidationResult, tree: ConflictTree
    ) -> list[RouteConflict]:
        emitted: list[RouteConflict] = []
        for node_id in tree.graph.nodes:
            node = tree.node(node_id)
            if node.state.status != "fail" or node.agent_result is None:
                continue
            finding = self._primary_finding(node.agent_result)
            if finding is None:
                continue
            kind = self._dead_end_kind(finding, validation)
            if kind is None:
                continue
            emitted.append(
                RouteConflict(
                    severity="blocking",
                    kind=kind,
                    description=finding.description,
                    affected=finding.affected or (),
                    resolution=self._process_resolution(node.agent_result.resolution),
                    provenance=(
                        inference_provenance(
                            "No surviving sibling at this branch point"
                        ),
                    ),
                )
            )
        return emitted

    def _winner_findings(
        self,
        validation: ValidationResult,
        tree: ConflictTree,
        selected_id: str | None,
        post_graph: PostGraphValidationReport,
    ) -> list[RouteConflict]:
        findings: list[tuple[AgentFinding, str | None]] = []
        if selected_id is not None:
            result = tree.node(selected_id).agent_result
            if result is not None:
                findings.extend((item, result.resolution) for item in result.findings)
        winner = next(
            (
                item
                for item in post_graph.candidates
                if item.node_id == selected_id and item.intent is not None
            ),
            None,
        )
        if winner is not None and winner.intent is not None:
            findings.extend(
                (item, winner.intent.resolution) for item in winner.intent.findings
            )
        sibling = self._surviving_sibling_process(tree, selected_id)
        emitted: list[RouteConflict] = []
        for item, source_resolution in findings:
            kind = cli_kind_from_agent(item.kind, validation)
            if kind is None:
                continue
            severity: ConflictSeverity = (
                "major" if kind == "intent_not_achieved" else "minor"
            )
            resolution = None
            if severity == "major":
                resolution = source_resolution or sibling
            emitted.append(
                RouteConflict(
                    severity=severity,
                    kind=kind,
                    description=item.description,
                    affected=item.affected,
                    resolution=resolution,
                    provenance=(
                        inference_provenance("Finding retained from the winning leaf"),
                    ),
                )
            )
        return emitted

    def _unmapped_product_conflicts(
        self,
        validation: ValidationResult,
        tree: ConflictTree,
        selected_id: str | None,
        post_graph: PostGraphValidationReport,
    ) -> list[RouteConflict]:
        markers = collect_unmapped_markers(tree, selected_id, post_graph)
        if not markers:
            return []
        families = unmapped_families(markers)
        family_text = ", ".join(sorted(families)) or "requested modification"
        emitted = [
            RouteConflict(
                severity="blocking",
                kind="building_block_availability",
                description=(
                    f"No catalog fragment instantiates {family_text}, so the analog "
                    "cannot be assembled as specified."
                ),
                affected=tuple(sorted(families)),
                resolution=None,
                provenance=(
                    inference_provenance(
                        "Product connectivity left an unmapped permanent family"
                    ),
                ),
            )
        ]
        if not any(
            binding.family.value in families for binding in validation.family_bindings
        ):
            return emitted
        emitted.append(
            RouteConflict(
                severity="major",
                kind="intent_not_achieved",
                description=(
                    f"The requested {family_text} never landed on the product, "
                    "so the stated design intent is not achieved."
                ),
                affected=tuple(sorted(families)),
                resolution=None,
                provenance=(
                    inference_provenance(
                        "Intent depends on a family that 2D connectivity "
                        "could not apply"
                    ),
                ),
            )
        )
        return emitted

    def _validation_gaps(
        self, validation: ValidationResult, selected_id: str | None
    ) -> list[RouteConflict]:
        emitted: list[RouteConflict] = []
        resin_gap = any(
            error.cause_type == "resin_unsupported" for error in validation.state.errors
        )
        if not resin_gap:
            return emitted
        severity: ConflictSeverity = "major" if selected_id is not None else "blocking"
        emitted.append(
            RouteConflict(
                severity=severity,
                kind="building_block_availability",
                description=(
                    "No resin or on-resin building block is assigned for the "
                    "requested C-terminus, so the analog cannot be assembled "
                    "as specified."
                ),
                affected=(),
                resolution=None,
                provenance=(
                    inference_provenance(
                        "Resin selection could not assign a support "
                        "without inventing chemistry"
                    ),
                ),
            )
        )
        if any(
            binding.family.value in ON_RESIN_FAMILIES
            for binding in validation.family_bindings
        ):
            emitted.append(
                RouteConflict(
                    severity="major",
                    kind="intent_not_achieved",
                    description=(
                        "The requested on-resin modification cannot be executed "
                        "without a resin, so the stated design intent is not achieved."
                    ),
                    affected=(),
                    resolution=None,
                    provenance=(
                        inference_provenance(
                            "On-resin family requested after resin selection failed"
                        ),
                    ),
                )
            )
        return emitted

    def _path_catalyst_conflicts(
        self, tree: ConflictTree, selected_id: str | None
    ) -> list[RouteConflict]:
        if selected_id is None:
            return []
        if path_has_kinds(tree, selected_id, CATALYST_KINDS):
            return []
        kind = path_catalyst_conflict_kind(tree, selected_id)
        if kind is None:
            return []
        resolution = None
        result = tree.node(selected_id).agent_result
        if result is not None:
            resolution = result.resolution
        return [
            RouteConflict(
                severity="major",
                kind=kind,
                description=(
                    "Palladium Alloc chemistry and ruthenium olefin metathesis "
                    "cannot share an unordered on-resin window."
                ),
                affected=(),
                resolution=resolution,
                provenance=(
                    inference_provenance(
                        "Pd and Ru catalysts appear on the same surviving path"
                    ),
                ),
            )
        ]

    def _terminus_chemistry_conflicts(
        self, validation: ValidationResult
    ) -> list[RouteConflict]:
        if not has_head_to_tail_amide_clash(validation):
            return []
        return [
            RouteConflict(
                severity="blocking",
                kind="mutually_exclusive",
                description=(
                    "Head-to-tail cyclization and C-terminal amidation compete for "
                    "the same alpha-carboxyl carbon."
                ),
                affected=("N-term", "C-term"),
                resolution=(
                    "Keep the C-terminal amide and close a side-chain lactam, "
                    "or drop amidation."
                ),
                provenance=(
                    inference_provenance(
                        "Resin-set C-terminal amide and head-to-tail closure "
                        "are two fates of one carboxyl carbon"
                    ),
                ),
            )
        ]

    def _dead_end_kind(
        self, finding: AgentFinding, validation: ValidationResult
    ) -> SchemaConflictKind | None:
        kind = cli_kind_from_agent(finding.kind, validation)
        if kind is None:
            return None
        if kind == "protecting_group_orthogonality" and self._missing_orthogonal_handle(
            finding
        ):
            return "building_block_availability"
        return kind

    def _missing_orthogonal_handle(self, finding: AgentFinding) -> bool:
        text = f"{finding.description} {' '.join(finding.affected)}".lower()
        return any(marker in text for marker in MISSING_HANDLE_MARKERS)

    def _first_process(
        self, validation: ValidationResult, modification_ref: int | None
    ) -> str | None:
        if modification_ref is None:
            return None
        for binding in validation.family_bindings:
            if binding.modification_ref == modification_ref and binding.process_ids:
                return binding.process_ids[0]
        return None

    def _primary_finding(self, result: AgentResult | None) -> AgentFinding | None:
        if result is None:
            return None
        for item in result.findings:
            if schema_kind(item.kind) is not None:
                return item
        return None

    def _surviving_sibling_process(
        self, tree: ConflictTree, selected_id: str | None
    ) -> str | None:
        if selected_id is None:
            return None
        path = collect_winning_path(tree, selected_id)
        for parent_id, child_id in zip(path, path[1:], strict=False):
            winner = tree.node(child_id)
            if winner.candidate is None:
                continue
            siblings = [
                tree.node(node_id) for node_id in tree.graph.successors(parent_id)
            ]
            if any(
                sibling.state.id != child_id and sibling.candidate is not None
                for sibling in siblings
            ):
                return winner.candidate.process
        return None

    def _process_resolution(self, resolution: str | None) -> str | None:
        if resolution is None or not resolution.strip():
            return None
        return resolution

    def _finding_provenance(
        self, failed: object, winner: object
    ) -> tuple[Provenance, ...]:
        return (
            inference_provenance(
                "First-tried process failed; surviving sibling kept the same site"
            ),
        )


def consolidate_conflicts(
    validation: ValidationResult,
    tree: ConflictTree,
    selected_id: str | None,
    post_graph: PostGraphValidationReport,
) -> tuple[RouteConflict, ...]:
    return ConflictConsolidator().consolidate(validation, tree, selected_id, post_graph)
