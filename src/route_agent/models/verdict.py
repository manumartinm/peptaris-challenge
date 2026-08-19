from __future__ import annotations

from typing import Literal

from route_agent.models.corpus import Provenance
from route_agent.models.frozen import FrozenModel
from route_agent.models.request import SiteMapEntry

Verdict = Literal[
    "feasible", "feasible_with_changes", "infeasible", "insufficient_information"
]
Confidence = Literal["high", "medium", "low"]
RouteStage = Literal[
    "resin_selection",
    "chain_assembly",
    "on_resin_modification",
    "n_terminal_cap",
    "cleavage",
    "solution_phase",
    "purification",
    "qc",
]
ConflictSeverity = Literal["blocking", "major", "minor"]
SchemaConflictKind = Literal[
    "protecting_group_orthogonality",
    "order_of_operations",
    "mutually_exclusive",
    "site_invalid",
    "reagent_incompatibility",
    "building_block_availability",
    "intent_not_achieved",
]


class RouteStep(FrozenModel):
    step: int
    stage: RouteStage
    operation: str
    provenance: tuple[Provenance, ...]


class RouteConflict(FrozenModel):
    severity: ConflictSeverity
    kind: SchemaConflictKind
    description: str
    affected: tuple[str, ...]
    resolution: str | None
    provenance: tuple[Provenance, ...]


class RouteVerdict(FrozenModel):
    request_id: str
    verdict: Verdict
    confidence: Confidence
    resolved_sequence: str | None
    resolved_annotations: dict[str, str]
    site_map: tuple[SiteMapEntry, ...]
    route: tuple[RouteStep, ...]
    conflicts: tuple[RouteConflict, ...]
    unknowns: tuple[str, ...]
