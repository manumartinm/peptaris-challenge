from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, TypedDict

import networkx as nx

from route_agent.models.agent import (
    AgentCandidate,
    AgentResult,
    CostReport,
    LLMCall,
    build_cost_report,
)
from route_agent.models.corpus import FamilyBinding, Provenance
from route_agent.models.frozen import FrozenModel
from route_agent.models.request import (
    IndexMapEntry,
    ParentCTerminus,
    Residue,
    ResolvedSite,
    SiteInvalidFinding,
    SiteMapEntry,
)
from route_agent.models.validation import StructuredFreeText, ValidationError

StateStatus = Literal["pass", "fail", "degraded"]
LEDGER_KEYS = ("protected", "free_amines", "catalysts_used", "termini")
BRANCH_KEYS = ("history",)
TOPOLOGY_KEYS = (
    "permanent_connectivity",
    "product_fragments",
    "residue_overrides",
    "n_methyl_sites",
    "product_unknowns",
)


class StateLedger(TypedDict, total=False):
    protected: dict[str, str]
    free_amines: dict[str, str]
    catalysts_used: dict[str, str]
    termini: dict[str, str]
    history: list[dict[str, Any]]
    applied: dict[str, Any]
    permanent_connectivity: list[dict[str, str]]
    product_fragments: list[dict[str, Any]]
    residue_overrides: dict[str, str]
    n_methyl_sites: list[str]


class State(FrozenModel):
    """One node in the conflict tree.

    ``output`` is the chemistry ledger. Expected keys are documented on
    ``StateLedger``; extra request-level fields are also stored there.
    """

    id: str
    node_type: str
    parents: tuple[str, ...]
    modification_ref: int | None
    status: StateStatus
    output: dict[str, Any]
    building_block: str | None
    sequence_snapshot: str | None
    route_step: dict[str, Any] | None
    errors: tuple[ValidationError, ...]
    provenance: tuple[Provenance, ...]
    llm_calls: tuple[LLMCall, ...]


class ProcessTrace(FrozenModel):
    family: str
    site: str
    process: str
    modification_ref: int
    passed: bool | None


class ConflictNode(FrozenModel):
    state: State
    candidate: AgentCandidate | None = None
    agent_result: AgentResult | None = None


class ConflictNodeReport(FrozenModel):
    id: str
    children: tuple[str, ...]
    state: State
    candidate: AgentCandidate | None = None
    agent_result: AgentResult | None = None


class ConflictTreeReport(FrozenModel):
    request_id: str
    root_id: str
    surviving_ids: tuple[str, ...]
    nodes: tuple[ConflictNodeReport, ...]
    cost: CostReport = CostReport()


@dataclass(frozen=True)
class ConflictTree:
    graph: nx.DiGraph[str]
    root_id: str
    surviving_ids: tuple[str, ...]

    def node(self, node_id: str) -> ConflictNode:
        stored = self.graph.nodes[node_id].get("node")
        if isinstance(stored, ConflictNode):
            return stored
        payload = self.graph.nodes[node_id]
        return ConflictNode(
            state=payload["state"],
            candidate=payload.get("candidate"),
            agent_result=payload.get("agent_result"),
        )

    def to_report(
        self, request_id: str, extra_calls: tuple[LLMCall, ...] = ()
    ) -> ConflictTreeReport:
        nodes = []
        calls = list(extra_calls)
        for node_id in self.graph.nodes:
            payload = self.node(node_id)
            nodes.append(
                ConflictNodeReport(
                    id=node_id,
                    children=tuple(self.graph.successors(node_id)),
                    state=payload.state,
                    candidate=payload.candidate,
                    agent_result=payload.agent_result,
                )
            )
            calls.extend(payload.state.llm_calls)
        return ConflictTreeReport(
            request_id=request_id,
            root_id=self.root_id,
            surviving_ids=self.surviving_ids,
            cost=build_cost_report(calls),
            nodes=tuple(nodes),
        )


class ValidationResult(FrozenModel):
    request_id: str
    state: State
    residues: tuple[Residue, ...]
    sites_resolved: tuple[ResolvedSite, ...]
    parent_c_terminus: ParentCTerminus
    parent_features: tuple[str, ...]
    residue_annotations: dict[str, str]
    occupancy: StructuredFreeText
    intent: str
    family_bindings: tuple[FamilyBinding, ...]
    resolved_sequence: str | None
    resolved_annotations: dict[str, str]
    index_map: tuple[IndexMapEntry, ...]
    site_map: tuple[SiteMapEntry, ...]
    conflicts: tuple[SiteInvalidFinding, ...]
    unknowns: tuple[str, ...]

    @property
    def parent_residue_annotations(self) -> dict[str, str]:
        return self.residue_annotations
