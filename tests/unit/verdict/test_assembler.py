from __future__ import annotations

from route_agent.models.agent import AgentCandidate, AgentResult, ProcessProfile
from route_agent.models.conflict import ConflictTree
from route_agent.models.corpus import FamilyBinding, Provenance
from route_agent.models.request import ModificationFamily, SiteInvalidFinding
from route_agent.parser.errors import ErrorFactory
from route_agent.verdict.assembler import assemble_route_verdict
from route_agent.verdict.conflicts import consolidate_conflicts
from route_agent.verdict.ladder import compute_verdict
from route_agent.verdict.route import reconstruct_route
from tests.support.conflict_fixtures import (
    empty_validation,
    finding,
    lipid_candidate,
    lipidation_binding,
    make_node,
    make_tree,
    post_graph_report,
    resin_node,
)


class FakeFamilies:
    def lookup_family_process(self, family: str, process_id: str) -> ProcessProfile:
        return ProcessProfile(
            family=family,
            process_id=process_id,
            found=True,
            name=process_id,
            stage_hint="on_resin_modification",
        )


def _sibling_tree(*, winner: str = "state_2", degraded: bool = False) -> ConflictTree:
    failed = AgentResult(
        objective="check_compatibility",
        passed=False,
        findings=(
            finding(
                "protecting_group_orthogonality",
                "Mtt is not orthogonal to tBu",
            ),
        ),
    )
    passed = AgentResult(
        objective="check_compatibility",
        passed=None if degraded else True,
        unknowns=("model disabled",) if degraded else (),
    )
    nodes = [
        resin_node(),
        make_node(
            "state_1",
            parents=("state_0",),
            status="fail",
            route_step=None,
            candidate=lipid_candidate("mtt_lipidation"),
            result=failed,
            modification_ref=0,
        ),
        make_node(
            "state_2",
            parents=("state_0",),
            status="degraded" if degraded else "pass",
            route_step={
                "family": "lipidation",
                "site": "K5",
                "process": "ivdde_lipidation",
            },
            candidate=lipid_candidate("ivdde_lipidation"),
            result=passed,
            modification_ref=0,
            output={"catalysts_used": {"Ru": "Grubbs"}, "protected": {}},
        ),
    ]
    return make_tree(
        nodes,
        [("state_0", "state_1"), ("state_0", "state_2")],
        surviving_ids=(winner,) if winner else (),
    )


class TestRouteReconstruction:
    def test_walks_parents_and_appends_deterministic_tail(self) -> None:
        tree = _sibling_tree()
        route = reconstruct_route(tree, "state_2", FakeFamilies())
        stages = [step.stage for step in route]
        assert stages[0] == "resin_selection"
        assert "chain_assembly" in stages
        assert "on_resin_modification" in stages
        assert stages[-3:] == ["cleavage", "purification", "qc"]
        assert any("ICP-MS" in step.operation for step in route if step.stage == "qc")
        assert all(step.provenance for step in route)

    def test_reconstructs_from_candidate_when_route_step_is_missing(self) -> None:
        tree = make_tree(
            [
                resin_node(),
                make_node(
                    "state_1",
                    parents=("state_0",),
                    status="degraded",
                    route_step=None,
                    candidate=lipid_candidate("alloc_lipidation"),
                    result=AgentResult(objective="check_compatibility", passed=None),
                    modification_ref=0,
                ),
            ],
            [("state_0", "state_1")],
            surviving_ids=("state_1",),
        )
        route = reconstruct_route(tree, "state_1", FakeFamilies())
        assert any("alloc_lipidation" in step.operation for step in route)
        assert any(step.stage == "on_resin_modification" for step in route)


class TestConflictConsolidation:
    def test_one_entry_per_branch_that_needed_a_sibling(self) -> None:
        tree = _sibling_tree()
        validation = empty_validation("T-SIB", bindings=(lipidation_binding(),))
        conflicts = consolidate_conflicts(
            validation,
            tree,
            "state_2",
            post_graph_report("T-SIB", selected_id="state_2"),
        )
        kinds = [item.kind for item in conflicts]
        assert kinds.count("protecting_group_orthogonality") == 1
        assert conflicts[0].resolution == "ivdde_lipidation"
        assert conflicts[0].severity == "major"

    def test_intent_failure_is_major(self) -> None:
        tree = _sibling_tree()
        intent = AgentResult(
            objective="check_intent",
            passed=False,
            findings=(finding("intent_not_achieved", "hits pharmacophore"),),
        )
        conflicts = consolidate_conflicts(
            empty_validation("T-INT", bindings=(lipidation_binding(),)),
            tree,
            "state_2",
            post_graph_report("T-INT", selected_id="state_2", intent=intent),
        )
        assert any(item.kind == "intent_not_achieved" for item in conflicts)
        assert all(
            item.severity == "major"
            for item in conflicts
            if item.kind == "intent_not_achieved"
        )

    def test_site_invalid_is_blocking(self) -> None:
        conflicts = consolidate_conflicts(
            empty_validation(
                "T-SITE",
                conflicts=(
                    SiteInvalidFinding(
                        description="K99 is outside the sequence",
                        affected=("K99",),
                        provenance=(
                            Provenance(
                                kind="inference",
                                basis="1-based parent sequence check",
                            ),
                        ),
                    ),
                ),
            ),
            make_tree([resin_node()], []),
            None,
            post_graph_report("T-SITE", selected_id=None),
        )
        assert conflicts[0].kind == "site_invalid"
        assert conflicts[0].severity == "blocking"

    def test_unsupported_resin_is_building_block_and_intent(self) -> None:
        resin_error = ErrorFactory().resin_error(
            parent_c_terminus="alcohol",
            amidation_requested=False,
            cyclization_anchor=False,
            message="No deterministic resin is assigned for an alcohol C-terminus",
        )
        peg_binding = FamilyBinding(
            modification_ref=0,
            family=ModificationFamily.PEGYLATION,
            sheet="07_PEGylation",
            process_ids=("pegylation_on_resin",),
            provenance=(Provenance(kind="inference", basis="unit test"),),
            site="K5",
        )
        root = resin_node().state.model_copy(
            update={"status": "degraded", "errors": (resin_error,), "route_step": None}
        )
        validation = empty_validation(
            "T-ALC",
            bindings=(peg_binding,),
            status="degraded",
            unknowns=(resin_error.message,),
        ).model_copy(update={"state": root})
        tree = make_tree([resin_node()], [])
        conflicts = consolidate_conflicts(
            validation, tree, None, post_graph_report("T-ALC", selected_id=None)
        )
        kinds = {item.kind for item in conflicts}
        assert "building_block_availability" in kinds
        assert "intent_not_achieved" in kinds

    def test_dead_end_missing_cys_handle_is_building_block(self) -> None:
        failed = AgentResult(
            objective="check_compatibility",
            passed=False,
            findings=(
                finding(
                    "protecting_group_orthogonality",
                    "No Cys(Acm) assignment is present; all cysteines remain Trt",
                    affected=("C1", "C6"),
                ),
            ),
        )
        tree = make_tree(
            [
                resin_node(),
                make_node(
                    "state_1",
                    parents=("state_0",),
                    status="fail",
                    candidate=AgentCandidate(
                        family="disulfide", site="C1-C6", process="regioselective"
                    ),
                    result=failed,
                    modification_ref=0,
                ),
            ],
            [("state_0", "state_1")],
        )
        validation = empty_validation("T-SS")
        report = post_graph_report("T-SS", selected_id=None)
        conflicts = consolidate_conflicts(validation, tree, None, report)
        assert all(item.kind == "building_block_availability" for item in conflicts)
        assert compute_verdict(validation, tree, report, conflicts) == (
            "insufficient_information"
        )

    def test_unmapped_family_is_insufficient_not_feasible(self) -> None:
        glyco = AgentCandidate(
            family="glycosylation",
            site="N28",
            process="deacetylation_with_dilute_hydrazine",
        )
        unknown = (
            "unmapped_permanent_family:glycosylation:"
            "deacetylation_with_dilute_hydrazine"
        )
        tree = make_tree(
            [
                resin_node(),
                make_node(
                    "state_1",
                    parents=("state_0",),
                    candidate=glyco,
                    result=AgentResult(objective="check_compatibility", passed=True),
                    modification_ref=0,
                    output={"product_unknowns": [unknown], "catalysts_used": {}},
                ),
            ],
            [("state_0", "state_1")],
            surviving_ids=("state_1",),
        )
        validation = empty_validation(
            "T-UNMAPPED",
            bindings=(
                FamilyBinding(
                    modification_ref=0,
                    family=ModificationFamily.GLYCOSYLATION,
                    sheet="08_Glycosylation",
                    process_ids=("deacetylation_with_dilute_hydrazine",),
                    provenance=(Provenance(kind="inference", basis="unit test"),),
                    site="N28",
                ),
            ),
        )
        report = post_graph_report(
            "T-UNMAPPED",
            selected_id="state_1",
            unknowns=(unknown,),
        )
        conflicts = consolidate_conflicts(validation, tree, "state_1", report)
        kinds = {item.kind for item in conflicts}
        assert "building_block_availability" in kinds
        assert "intent_not_achieved" in kinds
        assert compute_verdict(validation, tree, report, conflicts) == (
            "insufficient_information"
        )

    def test_agent_site_invalid_without_parser_is_remapped(self) -> None:
        failed = AgentResult(
            objective="check_compatibility",
            passed=False,
            findings=(
                finding(
                    "site_invalid",
                    "Rink amide cannot follow 2-CTC resin selection",
                    affected=("C-term",),
                ),
            ),
        )
        tree = make_tree(
            [
                resin_node(),
                make_node(
                    "state_1",
                    parents=("state_0",),
                    status="fail",
                    candidate=AgentCandidate(
                        family="c_term_amidation",
                        site="C-term",
                        process="c_term_amidation_default",
                    ),
                    result=failed,
                    modification_ref=1,
                ),
            ],
            [("state_0", "state_1")],
        )
        validation = empty_validation(
            "T-HT",
            bindings=(
                FamilyBinding(
                    modification_ref=0,
                    family=ModificationFamily.CYCLIZATION,
                    sheet="09_Cyclization",
                    process_ids=("head_to_tail_cyclization",),
                    provenance=(Provenance(kind="inference", basis="unit test"),),
                    site="both termini",
                ),
                FamilyBinding(
                    modification_ref=1,
                    family=ModificationFamily.C_TERM_AMIDATION,
                    sheet="04_C_Term_Amidation",
                    process_ids=("c_term_amidation_default",),
                    provenance=(Provenance(kind="inference", basis="unit test"),),
                    site="C-term",
                ),
            ),
        )
        report = post_graph_report("T-HT", selected_id=None)
        conflicts = consolidate_conflicts(validation, tree, None, report)
        kinds = {item.kind for item in conflicts}
        assert "mutually_exclusive" in kinds
        assert "site_invalid" not in kinds

    def test_pd_and_ru_on_path_are_order_not_orthogonality(self) -> None:
        tree = make_tree(
            [
                resin_node(),
                make_node(
                    "state_1",
                    parents=("state_0",),
                    candidate=AgentCandidate(
                        family="cyclization",
                        site="K26-D30",
                        process="side_chain_lactam",
                    ),
                    result=AgentResult(objective="check_compatibility", passed=True),
                    modification_ref=1,
                    output={"catalysts_used": {"Pd": "Pd(PPh3)4"}, "protected": {}},
                ),
                make_node(
                    "state_2",
                    parents=("state_1",),
                    candidate=AgentCandidate(
                        family="hydrocarbon_stapling",
                        site="V21,R25",
                        process="hydrocarbon_stapling_default",
                    ),
                    result=AgentResult(objective="check_compatibility", passed=True),
                    modification_ref=0,
                    output={"catalysts_used": {"Ru": "Grubbs"}, "protected": {}},
                ),
            ],
            [("state_0", "state_1"), ("state_1", "state_2")],
            surviving_ids=("state_2",),
        )
        conflicts = consolidate_conflicts(
            empty_validation("T-CATALYST"),
            tree,
            "state_2",
            post_graph_report("T-CATALYST", selected_id="state_2"),
        )
        kinds = [item.kind for item in conflicts]
        assert "protecting_group_orthogonality" not in kinds
        assert "order_of_operations" in kinds or "reagent_incompatibility" in kinds

    def test_intent_resolution_is_copied_to_conflict(self) -> None:
        tree = _sibling_tree()
        intent = AgentResult(
            objective="check_intent",
            passed=False,
            resolution="ivdde_lipidation",
            findings=(finding("intent_not_achieved", "hits pharmacophore"),),
        )
        conflicts = consolidate_conflicts(
            empty_validation("T-RES", bindings=(lipidation_binding(),)),
            tree,
            "state_2",
            post_graph_report("T-RES", selected_id="state_2", intent=intent),
        )
        intent_conflicts = [
            item for item in conflicts if item.kind == "intent_not_achieved"
        ]
        assert intent_conflicts
        assert intent_conflicts[0].resolution == "ivdde_lipidation"

    def test_two_on_resin_families_do_not_invent_orthogonality(self) -> None:
        tree = make_tree(
            [
                resin_node(),
                make_node(
                    "state_1",
                    parents=("state_0",),
                    route_step={
                        "family": "lipidation",
                        "site": "K13",
                        "process": "alloc_lipidation",
                    },
                    candidate=lipid_candidate("alloc_lipidation", site="K13"),
                    result=AgentResult(objective="check_compatibility", passed=True),
                    modification_ref=1,
                ),
                make_node(
                    "state_2",
                    parents=("state_1",),
                    route_step={
                        "family": "pegylation",
                        "site": "N-term",
                        "process": "pegylation_on_resin",
                    },
                    candidate=AgentCandidate(
                        family="pegylation",
                        site="N-term",
                        process="pegylation_on_resin",
                    ),
                    result=AgentResult(objective="check_compatibility", passed=True),
                    modification_ref=0,
                ),
            ],
            [("state_0", "state_1"), ("state_1", "state_2")],
            surviving_ids=("state_2",),
        )
        validation = empty_validation(
            "T-DUAL",
            bindings=(
                FamilyBinding(
                    modification_ref=0,
                    family=ModificationFamily.PEGYLATION,
                    sheet="07_PEGylation",
                    process_ids=("pegylation_on_resin",),
                    provenance=(Provenance(kind="inference", basis="unit test"),),
                    site="N-term",
                ),
                FamilyBinding(
                    modification_ref=1,
                    family=ModificationFamily.LIPIDATION,
                    sheet="06_Lipidation",
                    process_ids=("alloc_lipidation",),
                    provenance=(Provenance(kind="inference", basis="unit test"),),
                    site="K13",
                ),
            ),
        )
        conflicts = consolidate_conflicts(
            validation,
            tree,
            "state_2",
            post_graph_report("T-DUAL", selected_id="state_2"),
        )
        assert "protecting_group_orthogonality" not in {item.kind for item in conflicts}

    def test_three_on_resin_families_do_not_invent_pairwise_orthogonality(self) -> None:
        tree = make_tree(
            [
                resin_node(),
                make_node(
                    "state_1",
                    parents=("state_0",),
                    candidate=lipid_candidate("alloc_lipidation", site="K13"),
                    result=AgentResult(objective="check_compatibility", passed=True),
                    modification_ref=0,
                ),
                make_node(
                    "state_2",
                    parents=("state_1",),
                    candidate=AgentCandidate(
                        family="pegylation",
                        site="N-term",
                        process="pegylation_on_resin",
                    ),
                    result=AgentResult(objective="check_compatibility", passed=True),
                    modification_ref=1,
                ),
                make_node(
                    "state_3",
                    parents=("state_2",),
                    candidate=AgentCandidate(
                        family="cyclization",
                        site="K26-D30",
                        process="side_chain_lactam",
                    ),
                    result=AgentResult(objective="check_compatibility", passed=True),
                    modification_ref=2,
                ),
            ],
            [
                ("state_0", "state_1"),
                ("state_1", "state_2"),
                ("state_2", "state_3"),
            ],
            surviving_ids=("state_3",),
        )
        conflicts = consolidate_conflicts(
            empty_validation("T-TRI"),
            tree,
            "state_3",
            post_graph_report("T-TRI", selected_id="state_3"),
        )
        assert "protecting_group_orthogonality" not in {item.kind for item in conflicts}

    def test_non_schema_finding_kind_surfaces_as_unknown(self) -> None:
        tree = make_tree(
            [
                resin_node(),
                make_node(
                    "state_1",
                    parents=("state_0",),
                    candidate=lipid_candidate("alloc_lipidation"),
                    result=AgentResult(
                        objective="check_compatibility",
                        passed=True,
                        findings=(
                            finding("not_a_schema_kind", "model invented a kind"),
                        ),
                    ),
                    modification_ref=0,
                ),
            ],
            [("state_0", "state_1")],
            surviving_ids=("state_1",),
        )
        verdict = assemble_route_verdict(
            request_id="T-KIND",
            validation=empty_validation("T-KIND", bindings=(lipidation_binding(),)),
            tree=tree,
            post_graph=post_graph_report("T-KIND", selected_id="state_1"),
            families=FakeFamilies(),
            judge=None,
        )
        assert any(
            item.startswith("unreadable_conflict_kind:") for item in verdict.unknowns
        )

    def test_head_to_tail_plus_amidation_is_mutually_exclusive(self) -> None:
        validation = empty_validation(
            "T2",
            bindings=(
                FamilyBinding(
                    modification_ref=0,
                    family=ModificationFamily.CYCLIZATION,
                    sheet="09_Cyclization",
                    process_ids=("head_to_tail_cyclization",),
                    provenance=(Provenance(kind="inference", basis="unit test"),),
                    site="both termini",
                ),
                FamilyBinding(
                    modification_ref=1,
                    family=ModificationFamily.C_TERM_AMIDATION,
                    sheet="04_C_Term_Amidation",
                    process_ids=("c_term_amidation_default",),
                    provenance=(Provenance(kind="inference", basis="unit test"),),
                    site="C-term",
                ),
            ),
        )
        tree = make_tree([resin_node()], [])
        conflicts = consolidate_conflicts(
            validation, tree, None, post_graph_report("T2", selected_id=None)
        )
        assert any(item.kind == "mutually_exclusive" for item in conflicts)


class TestVerdictLadder:
    def test_clean_winner_is_feasible(self) -> None:
        tree = make_tree(
            [
                resin_node(),
                make_node(
                    "state_1",
                    parents=("state_0",),
                    route_step={
                        "family": "lipidation",
                        "site": "K5",
                        "process": "mtt_lipidation",
                    },
                    candidate=lipid_candidate("mtt_lipidation"),
                    result=AgentResult(objective="check_compatibility", passed=True),
                    modification_ref=0,
                ),
            ],
            [("state_0", "state_1")],
            surviving_ids=("state_1",),
        )
        validation = empty_validation(
            "T-CLEAN",
            bindings=(
                lipidation_binding().model_copy(
                    update={"process_ids": ("mtt_lipidation",)}
                ),
            ),
        )
        report = post_graph_report(
            "T-CLEAN",
            selected_id="state_1",
            intent=AgentResult(objective="check_intent", passed=True),
        )
        conflicts = consolidate_conflicts(validation, tree, "state_1", report)
        assert compute_verdict(validation, tree, report, conflicts) == "feasible"

    def test_sibling_workaround_is_feasible_with_changes(self) -> None:
        tree = _sibling_tree()
        validation = empty_validation("T-SIB", bindings=(lipidation_binding(),))
        report = post_graph_report("T-SIB", selected_id="state_2")
        conflicts = consolidate_conflicts(validation, tree, "state_2", report)
        assert (
            compute_verdict(validation, tree, report, conflicts)
            == "feasible_with_changes"
        )

    def test_degraded_model_path_is_insufficient(self) -> None:
        tree = _sibling_tree(degraded=True)
        validation = empty_validation("T-DEG", bindings=(lipidation_binding(),))
        report = post_graph_report(
            "T-DEG",
            selected_id="state_2",
            unknowns=("model disabled",),
        )
        conflicts = consolidate_conflicts(validation, tree, "state_2", report)
        assert (
            compute_verdict(validation, tree, report, conflicts)
            == "insufficient_information"
        )

    def test_degraded_census_on_winning_path_is_not_a_refusal(self) -> None:
        tree = make_tree(
            [
                make_node(
                    "state_0",
                    status="degraded",
                    route_step={
                        "stage": "resin_selection",
                        "resin": "Rink",
                        "operation": "Select Rink at the start of synthesis",
                    },
                ),
                make_node(
                    "state_1",
                    parents=("state_0",),
                    route_step={
                        "family": "special_residues",
                        "site": "X27",
                        "process": "handling_hindered_ncaa",
                    },
                    candidate=AgentCandidate(
                        family="special_residues",
                        site="X27",
                        process="handling_hindered_ncaa",
                    ),
                    result=AgentResult(objective="check_compatibility", passed=True),
                    modification_ref=0,
                ),
            ],
            [("state_0", "state_1")],
            surviving_ids=("state_1",),
        )
        validation = empty_validation("T-NLE", status="degraded")
        report = post_graph_report("T-NLE", selected_id="state_1")
        conflicts = consolidate_conflicts(validation, tree, "state_1", report)
        assert compute_verdict(validation, tree, report, conflicts) == "feasible"

    def test_site_invalid_is_infeasible(self) -> None:
        tree = make_tree([resin_node()], [])
        validation = empty_validation(
            "T-SITE",
            status="fail",
            conflicts=(
                SiteInvalidFinding(
                    description="bad site",
                    affected=("K99",),
                    provenance=(Provenance(kind="inference", basis="sequence check"),),
                ),
            ),
        )
        report = post_graph_report("T-SITE", selected_id=None)
        conflicts = consolidate_conflicts(validation, tree, None, report)
        assert compute_verdict(validation, tree, report, conflicts) == "infeasible"

    def test_no_survivors_with_explicit_fails_is_infeasible(self) -> None:
        failed = AgentResult(
            objective="check_compatibility",
            passed=False,
            findings=(finding("reagent_incompatibility", "no route"),),
        )
        tree = make_tree(
            [
                resin_node(),
                make_node(
                    "state_1",
                    parents=("state_0",),
                    status="fail",
                    candidate=lipid_candidate("mtt_lipidation"),
                    result=failed,
                    modification_ref=0,
                ),
            ],
            [("state_0", "state_1")],
        )
        validation = empty_validation("T-DEAD", bindings=(lipidation_binding(),))
        report = post_graph_report("T-DEAD", selected_id=None)
        conflicts = consolidate_conflicts(validation, tree, None, report)
        assert compute_verdict(validation, tree, report, conflicts) == "infeasible"


class TestAssembler:
    def test_merges_unknowns_and_does_not_write_extra_fields(self) -> None:
        tree = _sibling_tree()
        judge = AgentResult(
            objective="final_judge",
            confidence="medium",
            gaps=("qc metal check inferred",),
            unknowns=("no measured SAR",),
        )
        verdict = assemble_route_verdict(
            request_id="T-ASM",
            validation=empty_validation("T-ASM", bindings=(lipidation_binding(),)),
            tree=tree,
            post_graph=post_graph_report("T-ASM", selected_id="state_2"),
            families=FakeFamilies(),
            judge=judge,
        )
        assert verdict.verdict == "feasible_with_changes"
        assert verdict.confidence == "medium"
        assert "qc metal check inferred" in verdict.unknowns
        assert "no measured SAR" in verdict.unknowns
        assert set(verdict.model_dump(mode="json")) == {
            "request_id",
            "verdict",
            "confidence",
            "resolved_sequence",
            "resolved_annotations",
            "site_map",
            "route",
            "conflicts",
            "unknowns",
        }
