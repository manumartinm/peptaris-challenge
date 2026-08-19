from __future__ import annotations

from typing import Any

from route_agent.corpus import CorpusRepository
from route_agent.models.agent import ProcessProfile
from route_agent.models.conflict import ConflictNode, ConflictTree
from route_agent.models.corpus import Provenance, inference_provenance
from route_agent.models.verdict import RouteStage, RouteStep
from route_agent.verdict.path import collect_winning_path

FAMILY_STAGE: dict[str, RouteStage] = {
    "spps_foundation": "chain_assembly",
    "special_residues": "chain_assembly",
    "n_methylation": "chain_assembly",
    "c_term_amidation": "resin_selection",
    "n_term_acetylation": "n_terminal_cap",
    "lipidation": "on_resin_modification",
    "pegylation": "on_resin_modification",
    "glycosylation": "on_resin_modification",
    "cyclization": "on_resin_modification",
    "hydrocarbon_stapling": "on_resin_modification",
    "disulfide": "solution_phase",
    "biaryl_bisalkylation": "on_resin_modification",
    "aza_peptide": "chain_assembly",
    "retro_inverso": "chain_assembly",
    "charge_hybrids": "on_resin_modification",
}

TAIL: tuple[tuple[RouteStage, str], ...] = (
    ("cleavage", "Cleave from resin and remove side-chain protecting groups"),
    ("purification", "Purify the crude peptide by RP-HPLC"),
    ("qc", "Confirm identity by LC-MS"),
)


class RouteReconstructor:
    def __init__(self, families: CorpusRepository | Any) -> None:
        self._families = families

    def reconstruct(
        self, tree: ConflictTree, selected_id: str | None
    ) -> tuple[RouteStep, ...]:
        drafted: list[tuple[RouteStage, str, tuple[Provenance, ...]]] = []
        for node_id in collect_winning_path(tree, selected_id):
            converted = self._step_from_node(tree.node(node_id))
            if converted is not None:
                drafted.append(converted)
        drafted = self._ensure_chain_assembly(drafted)
        drafted.extend(self._tail_steps(tree, selected_id))
        return tuple(
            RouteStep(
                step=index,
                stage=stage,
                operation=operation,
                provenance=provenance,
            )
            for index, (stage, operation, provenance) in enumerate(drafted, start=1)
        )

    def _step_from_node(
        self, node: ConflictNode
    ) -> tuple[RouteStage, str, tuple[Provenance, ...]] | None:
        payload = node.state.route_step
        if not payload and node.candidate is not None:
            payload = {
                "family": node.candidate.family,
                "site": node.candidate.site,
                "process": node.candidate.process,
            }
        if not payload:
            return None
        if payload.get("stage") == "resin_selection":
            operation = payload.get("operation") or (
                f"Select {payload.get('resin', 'resin')} at the start of synthesis"
            )
            provenance = node.state.provenance or (
                inference_provenance("Resin choice is made before chain assembly"),
            )
            return ("resin_selection", str(operation), provenance)
        family = str(payload.get("family") or "")
        process = str(payload.get("process") or "")
        site = str(payload.get("site") or "")
        profile = self._lookup_profile(family, process)
        stage = self._stage_for(profile, family)
        operation = (
            f"Apply {profile.name or process} at {site}"
            if site
            else f"Apply {profile.name or process}"
        )
        return (stage, operation, self._provenance_for(profile, node, process))

    def _lookup_profile(self, family: str, process: str) -> ProcessProfile:
        lookup = getattr(self._families, "lookup_family_process", None)
        if callable(lookup) and family and process:
            profile = lookup(family, process)
            if isinstance(profile, ProcessProfile):
                return profile
        return ProcessProfile(family=family, process_id=process, found=False)

    def _stage_for(self, profile: ProcessProfile, family: str) -> RouteStage:
        hint = profile.stage_hint
        if hint in FAMILY_STAGE.values() or hint in {
            "resin_selection",
            "chain_assembly",
            "on_resin_modification",
            "n_terminal_cap",
            "cleavage",
            "solution_phase",
            "purification",
            "qc",
        }:
            return hint  # type: ignore[return-value]
        return FAMILY_STAGE.get(family, "on_resin_modification")

    def _provenance_for(
        self, profile: ProcessProfile, node: ConflictNode, process: str
    ) -> tuple[Provenance, ...]:
        cited: list[Provenance] = []
        for fact in (
            *profile.reagents,
            *profile.conditions,
            *profile.constraints,
        ):
            if fact.ref:
                cited.append(Provenance(kind="corpus", ref=fact.ref))
        if cited:
            unique: list[Provenance] = []
            seen: set[str] = set()
            for item in cited:
                key = item.ref or ""
                if key in seen:
                    continue
                seen.add(key)
                unique.append(item)
            return tuple(unique)
        if node.state.provenance:
            return node.state.provenance
        return (inference_provenance(f"Apply process {process} at the requested site"),)

    def _ensure_chain_assembly(
        self,
        drafted: list[tuple[RouteStage, str, tuple[Provenance, ...]]],
    ) -> list[tuple[RouteStage, str, tuple[Provenance, ...]]]:
        if any(stage == "chain_assembly" for stage, _operation, _prov in drafted):
            return drafted
        assembly: tuple[RouteStage, str, tuple[Provenance, ...]] = (
            "chain_assembly",
            "Assemble the peptide backbone by Fmoc SPPS",
            (inference_provenance("Standard Fmoc chain assembly after resin loading"),),
        )
        insert_at = 0
        for index, (stage, _operation, _prov) in enumerate(drafted):
            if stage == "resin_selection":
                insert_at = index + 1
        drafted.insert(insert_at, assembly)
        return drafted

    def _tail_steps(
        self, tree: ConflictTree, selected_id: str | None
    ) -> list[tuple[RouteStage, str, tuple[Provenance, ...]]]:
        node = tree.node(selected_id) if selected_id else tree.node(tree.root_id)
        catalysts = node.state.output.get("catalysts_used") or {}
        tail: list[tuple[RouteStage, str, tuple[Provenance, ...]]] = []
        for stage, operation in TAIL:
            text = operation
            if stage == "qc" and catalysts:
                text = f"{operation} and residual metals by ICP-MS"
            tail.append(
                (
                    stage,
                    text,
                    (inference_provenance(f"Deterministic {stage} tail"),),
                )
            )
        return tail


def reconstruct_route(
    tree: ConflictTree,
    selected_id: str | None,
    families: CorpusRepository | Any,
) -> tuple[RouteStep, ...]:
    return RouteReconstructor(families).reconstruct(tree, selected_id)
