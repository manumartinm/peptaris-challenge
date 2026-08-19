from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from route_agent.models.corpus import Provenance
from route_agent.models.request import (
    DesignRequest,
    ModificationFamily,
    ParentCTerminus,
    Residue,
    ResolvedSite,
)
from route_agent.models.validation import (
    ProtectionLedger,
    ProtectionResult,
    ResinResult,
    ResinSelection,
)
from route_agent.parser.errors import ErrorFactory
from route_agent.parser.sites import sites_by_modification_ref

DEFAULT_SIDE_CHAIN = {
    "C": "Trt",
    "D": "OtBu",
    "E": "OtBu",
    "H": "Trt",
    "K": "Boc",
    "N": "Trt",
    "Q": "Trt",
    "R": "Pbf",
    "S": "tBu",
    "T": "tBu",
    "W": "Boc",
    "Y": "tBu",
}

BRANCHING_FAMILIES = frozenset(
    {
        ModificationFamily.LIPIDATION,
        ModificationFamily.PEGYLATION,
        ModificationFamily.GLYCOSYLATION,
        ModificationFamily.CYCLIZATION,
        ModificationFamily.HYDROCARBON_STAPLING,
        ModificationFamily.BIARYL_BISALKYLATION,
        ModificationFamily.CHARGE_HYBRIDS,
    }
)


@dataclass(frozen=True)
class ChemistryPolicy:
    policy_version: str = "fmoc-tbu-v1"
    default_side_chain: dict[str, str] = field(
        default_factory=lambda: dict(DEFAULT_SIDE_CHAIN)
    )
    branching_families: frozenset[ModificationFamily] = field(
        default_factory=lambda: BRANCHING_FAMILIES
    )
    rink: str = "Rink amide MBHA / ChemMatrix"
    wang: str = "Wang"
    ctc: str = "2-chlorotrityl chloride (2-CTC)"
    nonstandard: dict[str, str] = field(
        default_factory=lambda: {
            "NLE": "Nle",
            "AIB": "Aib",
            "CIT": "Cit",
            "ORN": "Orn",
            "NAL": "Nal",
            "THREONINOL": "threoninol",
            "THR-OL": "threoninol",
        }
    )


DEFAULT_CHEMISTRY = ChemistryPolicy()


class ProtectingGroupCensus:
    def __init__(
        self,
        errors: ErrorFactory | None = None,
        chemistry: ChemistryPolicy | None = None,
    ) -> None:
        self._errors = errors or ErrorFactory()
        self._chemistry = chemistry or DEFAULT_CHEMISTRY

    def census_protecting_groups(
        self,
        request: DesignRequest,
        residues: Sequence[Residue],
        sites: Sequence[ResolvedSite],
    ) -> ProtectionResult:
        protected: dict[str, str] = {}
        errors = []
        for residue in residues:
            if residue.letter == "X":
                errors.append(
                    self._errors.protecting_group_error(
                        token=residue.token,
                        annotation=residue.annotation,
                        index=residue.index,
                        message=(
                            f"{residue.token} has no standard side-chain protecting "
                            f"group in policy {self._chemistry.policy_version}."
                        ),
                    )
                )
                continue
            group = self._chemistry.default_side_chain.get(residue.letter)
            if group is not None:
                protected[residue.token] = group

        by_ref = sites_by_modification_ref(sites)
        for index, modification in enumerate(request.modifications):
            if modification.family not in self._chemistry.branching_families:
                continue
            site = by_ref.get(index)
            if site is None:
                continue
            for atom in site.atoms:
                if atom.kind in {"position", "n_term", "c_term"}:
                    protected[atom.token] = "pending"

        return ProtectionResult(
            ledger=ProtectionLedger(
                protected=protected,
                policy_version=self._chemistry.policy_version,
                provenance=(
                    Provenance(
                        kind="inference",
                        basis=(
                            "Hard-coded Fmoc/tBu side-chain census "
                            f"{self._chemistry.policy_version}; "
                            "branching family targets start as pending."
                        ),
                    ),
                ),
            ),
            errors=tuple(errors),
        )


class ResinSelector:
    def __init__(
        self,
        errors: ErrorFactory | None = None,
        chemistry: ChemistryPolicy | None = None,
    ) -> None:
        self._errors = errors or ErrorFactory()
        self._chemistry = chemistry or DEFAULT_CHEMISTRY

    def select_resin(self, request: DesignRequest) -> ResinResult:
        cyclization_anchor = any(
            modification.family == ModificationFamily.CYCLIZATION
            for modification in request.modifications
        )
        amidation_requested = any(
            modification.family == ModificationFamily.C_TERM_AMIDATION
            for modification in request.modifications
        )
        if cyclization_anchor:
            return self._build_resin_selection(
                resin=self._chemistry.ctc,
                request=request,
                cyclization_anchor=True,
                amidation_requested=amidation_requested,
                basis=(
                    "Cyclization anchor requested; 2-CTC is the corpus-supported "
                    "side-chain / protected-C-terminus handle."
                ),
                refs=("ApexChem_Synthesis_Reactions_by_AminoAcid:09_Cyclization:4",),
            )
        if amidation_requested or request.parent_c_terminus == ParentCTerminus.AMIDE:
            return self._build_resin_selection(
                resin=self._chemistry.rink,
                request=request,
                cyclization_anchor=False,
                amidation_requested=amidation_requested,
                basis=(
                    "C-terminal amide is requested or already present; Rink amide "
                    "sets the terminus at the start of synthesis."
                ),
                refs=(
                    "ApexChem_Synthesis_Reactions_by_AminoAcid:04_C_Term_Amidation:12",
                ),
            )
        if request.parent_c_terminus == ParentCTerminus.FREE_ACID:
            return self._build_resin_selection(
                resin=self._chemistry.wang,
                request=request,
                cyclization_anchor=False,
                amidation_requested=False,
                basis=(
                    "Linear free-acid parent uses Wang; 2-CTC is reserved for "
                    "cyclization anchors."
                ),
                refs=(
                    "ApexChem_Synthesis_Reactions_by_AminoAcid:01_SPPS_Foundation:4",
                ),
            )
        return ResinResult(
            selection=None,
            errors=(
                self._errors.resin_error(
                    parent_c_terminus=request.parent_c_terminus.value,
                    amidation_requested=amidation_requested,
                    cyclization_anchor=cyclization_anchor,
                    message=(
                        "No deterministic resin is assigned for an alcohol C-terminus "
                        "without fabricating chemistry."
                    ),
                ),
            ),
        )

    def _build_resin_selection(
        self,
        *,
        resin: str,
        request: DesignRequest,
        cyclization_anchor: bool,
        amidation_requested: bool,
        basis: str,
        refs: tuple[str, ...],
    ) -> ResinResult:
        provenance = (Provenance(kind="inference", basis=basis, refs=refs),)
        return ResinResult(
            selection=ResinSelection(
                resin=resin,
                operation=f"Select {resin} at the start of synthesis",
                cyclization_anchor_requested=cyclization_anchor,
                amidation_requested=amidation_requested,
                parent_c_terminus=request.parent_c_terminus,
                provenance=provenance,
                route_step={
                    "stage": "resin_selection",
                    "resin": resin,
                    "operation": f"Select {resin} at the start of synthesis",
                },
            ),
            errors=(),
        )
