from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Protocol

from rdkit import Chem
from rdkit.Chem import rdMolDescriptors

from route_agent.models.molecular import (
    CandidateMolecularValidation,
    ConformerEnsemble,
    MolecularIssue,
    MolecularRecipe,
    PhyschemDescriptors,
    TwoDValidation,
)
from route_agent.molecular.boltz import BoltzClient, sequence_only_issue
from route_agent.molecular.builder import MolecularBuilder
from route_agent.observability import StructuredLogger

Ionizable = tuple[str, float, str]


class StructurePredictor(Protocol):
    def predict_structure(self, recipe: MolecularRecipe) -> ConformerEnsemble: ...


@dataclass(frozen=True)
class MolecularConfig:
    ph: float = 7.4
    num_conformers: int = 20
    seed: int = 17
    timeout_s: float = 60.0
    max_heavy_atoms: int = 500
    rmsd_threshold: float = 0.75
    clash_scale: float = 0.7
    skip_3d: bool = False
    no_model: bool = False
    boltz_api_key: str | None = None
    boltz_timeout_s: float = 180.0


class MolecularAnalyzer:
    def __init__(
        self,
        builder: MolecularBuilder | None = None,
        config: MolecularConfig | None = None,
        logger: StructuredLogger | None = None,
        boltz: StructurePredictor | None = None,
    ) -> None:
        self._builder = builder or MolecularBuilder()
        self._config = config or MolecularConfig()
        self._logger = logger or StructuredLogger("route_agent.molecular")
        self._boltz = boltz

    @property
    def config(self) -> MolecularConfig:
        return self._config

    def bind_logger(self, logger: StructuredLogger) -> None:
        self._logger = logger

    def validate(
        self, recipe: MolecularRecipe, *, node_id: str
    ) -> CandidateMolecularValidation:
        started = perf_counter()
        self._logger.info(
            "molecular_build_start",
            node_id=node_id,
            sequence_len=len(recipe.sequence),
            fragments=len(recipe.fragments),
            n_methyl_sites=len(recipe.n_methyl_sites),
            skip_3d=self._config.skip_3d,
        )
        built = self._builder.build(recipe)
        unknowns = list(recipe.unknowns)
        unknowns.extend(issue.message for issue in built.two_d_validation.issues)
        unmapped = tuple(
            item
            for item in recipe.unknowns
            if item.startswith("unmapped_permanent_family:")
        )
        if unmapped:
            issues = list(built.two_d_validation.issues) + [
                MolecularIssue(
                    code="unmapped_family",
                    message=item,
                    path="product",
                )
                for item in unmapped
            ]
            return CandidateMolecularValidation(
                node_id=node_id,
                two_d=TwoDValidation(valid=False, issues=tuple(issues)),
                recipe=recipe,
                fragments=recipe.fragments,
                unknowns=tuple(unknowns),
            )
        self._logger.info(
            "molecular_two_d_done",
            node_id=node_id,
            valid=built.two_d_validation.valid,
            formula=built.two_d_validation.formula,
            exact_mw=built.two_d_validation.exact_mw,
            issues=len(built.two_d_validation.issues),
            duration_ms=_elapsed_ms(started),
        )
        if not built.two_d_validation.valid or built.mol is None:
            return CandidateMolecularValidation(
                node_id=node_id,
                two_d=built.two_d_validation,
                recipe=recipe,
                fragments=recipe.fragments,
                unknowns=tuple(unknowns),
            )
        descriptors = compute_physchem_descriptors(
            built.mol, built.ionizable, ph=self._config.ph
        )
        self._logger.info(
            "molecular_descriptors_done",
            node_id=node_id,
            ph=descriptors.ph,
            heavy_atoms=descriptors.heavy_atoms,
            exact_mw=built.two_d_validation.exact_mw,
        )
        ensemble, skip_reason = self._structure_3d(recipe, node_id=node_id)
        if skip_reason:
            unknowns.append(f"boltz_skipped:{skip_reason}")
        if ensemble is not None:
            unknowns.extend(issue.message for issue in ensemble.issues)
            only = sequence_only_issue(recipe)
            if only is not None and only.message not in unknowns:
                unknowns.append(only.message)
        return CandidateMolecularValidation(
            node_id=node_id,
            two_d=built.two_d_validation,
            descriptors=descriptors,
            ensemble=ensemble,
            recipe=recipe,
            fragments=recipe.fragments,
            unknowns=tuple(unknowns),
        )

    def _structure_3d(
        self, recipe: MolecularRecipe, *, node_id: str
    ) -> tuple[ConformerEnsemble | None, str | None]:
        if self._config.skip_3d:
            self._logger.info(
                "molecular_ensemble_skipped", node_id=node_id, reason="skip_3d"
            )
            return None, "skip_3d"
        if self._config.no_model:
            self._logger.info(
                "molecular_ensemble_skipped", node_id=node_id, reason="no_model"
            )
            return None, "no_model"
        if not self._config.boltz_api_key and self._boltz is None:
            self._logger.info(
                "molecular_ensemble_skipped", node_id=node_id, reason="no_boltz_key"
            )
            return None, "no_boltz_key"
        ensemble_started = perf_counter()
        self._logger.info(
            "molecular_ensemble_start",
            node_id=node_id,
            timeout_s=self._config.boltz_timeout_s,
            source="boltz",
        )
        client = self._boltz or BoltzClient(
            self._config.boltz_api_key or "",
            timeout_s=self._config.boltz_timeout_s,
        )
        ensemble = client.predict_structure(recipe)
        self._logger.info(
            "molecular_ensemble_done",
            node_id=node_id,
            embedding_ok=ensemble.embedding_ok,
            converged=ensemble.converged,
            forcefield=ensemble.forcefield,
            structure_confidence=ensemble.structure_confidence,
            issues=len(ensemble.issues),
            duration_ms=_elapsed_ms(ensemble_started),
        )
        return ensemble, None


def compute_physchem_descriptors(
    mol: Chem.Mol,
    ionizable: tuple[Ionizable, ...],
    *,
    ph: float = 7.4,
) -> PhyschemDescriptors:
    return PhyschemDescriptors(
        tpsa=float(rdMolDescriptors.CalcTPSA(mol)),
        clogp=float(rdMolDescriptors.CalcCrippenDescriptors(mol)[0]),
        hbd=int(rdMolDescriptors.CalcNumHBD(mol)),
        hba=int(rdMolDescriptors.CalcNumHBA(mol)),
        formal_charge=int(Chem.GetFormalCharge(mol)),
        rotatable_bonds=int(rdMolDescriptors.CalcNumRotatableBonds(mol)),
        rings=int(rdMolDescriptors.CalcNumRings(mol)),
        heavy_atoms=int(mol.GetNumHeavyAtoms()),
        net_charge=net_charge_at_ph(ionizable, ph),
        isoelectric_point=isoelectric_point(ionizable),
        ph=ph,
    )


def net_charge_at_ph(ionizable: tuple[Ionizable, ...], ph: float) -> float:
    return sum(_partial_charge(pka, kind, ph) for _name, pka, kind in ionizable)


def isoelectric_point(ionizable: tuple[Ionizable, ...]) -> float:
    if not ionizable:
        return 7.0
    low, high = 0.0, 14.0
    for _ in range(40):
        mid = (low + high) / 2
        if net_charge_at_ph(ionizable, mid) > 0:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def _partial_charge(pka: float, kind: str, ph: float) -> float:
    if kind == "acid":
        return -1.0 / (1.0 + 10 ** (pka - ph))
    return 1.0 / (1.0 + 10 ** (ph - pka))


def _elapsed_ms(started: float) -> int:
    return int((perf_counter() - started) * 1000)
