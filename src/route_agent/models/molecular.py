from __future__ import annotations

from typing import Any, Literal

from route_agent.models.agent import AgentCandidate, AgentResult, CostReport
from route_agent.models.frozen import FrozenModel

ForceFieldName = Literal["MMFF94s", "UFF", "none", "boltz"]
TerminusKind = Literal[
    "free",
    "acetyl",
    "amide",
    "acid",
    "alcohol",
    "malonyl",
    "gem_diamino",
    "peg4",
    "peg8",
]


class Bond(FrozenModel):
    from_atom: str
    to_fragment: str
    bond_type: str


class MolecularIssue(FrozenModel):
    code: str
    message: str
    path: str | None = None


class ProductFragment(FrozenModel):
    instance_id: str
    catalog_id: str
    site: str | None = None


class MolecularRecipe(FrozenModel):
    sequence: str
    annotations: dict[str, str]
    n_terminus: TerminusKind
    c_terminus: TerminusKind
    n_methyl_sites: tuple[str, ...] = ()
    bonds: tuple[Bond, ...] = ()
    fragments: tuple[ProductFragment, ...] = ()
    residue_overrides: dict[str, str] = {}
    unknowns: tuple[str, ...] = ()


class TwoDValidation(FrozenModel):
    valid: bool
    formula: str | None = None
    exact_mw: float | None = None
    smiles: str | None = None
    issues: tuple[MolecularIssue, ...] = ()


class PhyschemDescriptors(FrozenModel):
    tpsa: float
    clogp: float
    hbd: int
    hba: int
    formal_charge: int
    rotatable_bonds: int
    rings: int
    heavy_atoms: int
    net_charge: float
    isoelectric_point: float
    ph: float


class ConformerEnsemble(FrozenModel):
    embedding_ok: bool
    converged: bool
    n_requested: int
    n_embedded: int
    n_optimized: int
    valid_fraction: float
    forcefield: ForceFieldName
    n_clashes: int
    radius_of_gyration: float | None = None
    asphericity: float | None = None
    npr1: float | None = None
    npr2: float | None = None
    pmi1: float | None = None
    pmi2: float | None = None
    pmi3: float | None = None
    best_energy: float | None = None
    sdf: str | None = None
    cif: str | None = None
    structure_confidence: float | None = None
    ptm: float | None = None
    complex_plddt: float | None = None
    issues: tuple[MolecularIssue, ...] = ()


class CandidateMolecularValidation(FrozenModel):
    node_id: str
    two_d: TwoDValidation
    descriptors: PhyschemDescriptors | None = None
    ensemble: ConformerEnsemble | None = None
    recipe: MolecularRecipe | None = None
    fragments: tuple[ProductFragment, ...] = ()
    unknowns: tuple[str, ...] = ()


class CandidatePostGraphResult(FrozenModel):
    node_id: str
    candidate: AgentCandidate | None = None
    molecular: CandidateMolecularValidation
    intent: AgentResult | None = None
    rank: tuple[int, ...] = ()


class PostGraphValidationReport(FrozenModel):
    request_id: str
    surviving_ids: tuple[str, ...]
    selected_id: str | None
    tied_ids: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()
    candidates: tuple[CandidatePostGraphResult, ...] = ()
    extra: dict[str, Any] = {}
    cost: CostReport = CostReport()
