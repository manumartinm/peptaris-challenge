from __future__ import annotations

from typing import Any

import networkx as nx

from route_agent.models.agent import AgentCandidate, AgentFinding, AgentResult
from route_agent.models.conflict import (
    ConflictNode,
    ConflictTree,
    State,
    ValidationResult,
)
from route_agent.models.corpus import FamilyBinding, Provenance
from route_agent.models.molecular import (
    CandidateMolecularValidation,
    CandidatePostGraphResult,
    PostGraphValidationReport,
    TwoDValidation,
)
from route_agent.models.request import (
    ModificationFamily,
    ParentCTerminus,
    SiteInvalidFinding,
    SiteMapEntry,
)
from route_agent.models.validation import StructuredFreeText


def make_state(
    node_id: str,
    *,
    parents: tuple[str, ...] = (),
    status: str = "pass",
    route_step: dict[str, Any] | None = None,
    output: dict[str, Any] | None = None,
    modification_ref: int | None = None,
) -> State:
    return State(
        id=node_id,
        node_type="validation" if node_id == "state_0" else "candidate",
        parents=parents,
        modification_ref=modification_ref,
        status=status,  # type: ignore[arg-type]
        output=output or {"catalysts_used": {}, "protected": {}},
        building_block=None,
        sequence_snapshot="ACDEK",
        route_step=route_step,
        errors=(),
        provenance=(),
        llm_calls=(),
    )


def make_node(
    node_id: str,
    *,
    parents: tuple[str, ...] = (),
    status: str = "pass",
    route_step: dict[str, Any] | None = None,
    candidate: AgentCandidate | None = None,
    result: AgentResult | None = None,
    output: dict[str, Any] | None = None,
    modification_ref: int | None = None,
) -> ConflictNode:
    return ConflictNode(
        state=make_state(
            node_id,
            parents=parents,
            status=status,
            route_step=route_step,
            output=output,
            modification_ref=modification_ref,
        ),
        candidate=candidate,
        agent_result=result,
    )


def make_tree(
    nodes: list[ConflictNode],
    edges: list[tuple[str, str]],
    *,
    root_id: str = "state_0",
    surviving_ids: tuple[str, ...] = (),
) -> ConflictTree:
    graph: nx.DiGraph[str] = nx.DiGraph()
    for node in nodes:
        graph.add_node(node.state.id, node=node)
    for parent, child in edges:
        graph.add_edge(parent, child)
    return ConflictTree(graph=graph, root_id=root_id, surviving_ids=surviving_ids)


def resin_node() -> ConflictNode:
    return make_node(
        "state_0",
        route_step={
            "stage": "resin_selection",
            "resin": "Wang",
            "operation": "Select Wang at the start of synthesis",
        },
        output={"catalysts_used": {}, "protected": {}, "resin": "Wang"},
    )


def lipid_candidate(process: str, site: str = "K5") -> AgentCandidate:
    return AgentCandidate(family="lipidation", site=site, process=process)


def lipidation_binding() -> FamilyBinding:
    return FamilyBinding(
        modification_ref=0,
        family=ModificationFamily.LIPIDATION,
        sheet="06_Lipidation",
        process_ids=("mtt_lipidation", "ivdde_lipidation"),
        provenance=(
            Provenance(
                kind="corpus",
                ref="ApexChem_Synthesis_Reactions_by_AminoAcid:06_Lipidation:8",
            ),
        ),
        site="K5",
    )


def empty_validation(
    request_id: str,
    *,
    bindings: tuple[FamilyBinding, ...] = (),
    conflicts: tuple[SiteInvalidFinding, ...] = (),
    unknowns: tuple[str, ...] = (),
    status: str = "pass",
) -> ValidationResult:
    root = resin_node().state
    if status != "pass":
        root = root.model_copy(update={"status": status})
    return ValidationResult(
        request_id=request_id,
        state=root,
        residues=(),
        sites_resolved=(),
        parent_c_terminus=ParentCTerminus.FREE_ACID,
        parent_features=(),
        residue_annotations={},
        occupancy=StructuredFreeText(features=(), occupancy=(), route_seed=()),
        intent="unit test",
        family_bindings=bindings,
        resolved_sequence="ACDEK",
        resolved_annotations={},
        index_map=(),
        site_map=(
            SiteMapEntry(requested="K5", resolved="K5", residue="Lys", note=None),
        ),
        conflicts=conflicts,
        unknowns=unknowns,
    )


def post_graph_report(
    request_id: str,
    *,
    selected_id: str | None,
    surviving_ids: tuple[str, ...] = (),
    intent: AgentResult | None = None,
    unknowns: tuple[str, ...] = (),
) -> PostGraphValidationReport:
    candidates: tuple[CandidatePostGraphResult, ...] = ()
    if selected_id is not None:
        candidates = (
            CandidatePostGraphResult(
                node_id=selected_id,
                candidate=lipid_candidate("ivdde_lipidation"),
                molecular=CandidateMolecularValidation(
                    node_id=selected_id,
                    two_d=TwoDValidation(valid=True, formula="C2H5NO2", exact_mw=75.0),
                ),
                intent=intent,
            ),
        )
    return PostGraphValidationReport(
        request_id=request_id,
        surviving_ids=surviving_ids or ((selected_id,) if selected_id else ()),
        selected_id=selected_id,
        unknowns=unknowns,
        candidates=candidates,
    )


def finding(
    kind: str, description: str, affected: tuple[str, ...] = ("K5",)
) -> AgentFinding:
    return AgentFinding(kind=kind, description=description, affected=affected)
