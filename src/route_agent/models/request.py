from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from route_agent.models.frozen import FrozenModel


class ParentCTerminus(StrEnum):
    FREE_ACID = "free_acid"
    AMIDE = "amide"
    ALCOHOL = "alcohol"


class ModificationFamily(StrEnum):
    SPPS_FOUNDATION = "spps_foundation"
    SPECIAL_RESIDUES = "special_residues"
    N_METHYLATION = "n_methylation"
    C_TERM_AMIDATION = "c_term_amidation"
    N_TERM_ACETYLATION = "n_term_acetylation"
    LIPIDATION = "lipidation"
    PEGYLATION = "pegylation"
    GLYCOSYLATION = "glycosylation"
    CYCLIZATION = "cyclization"
    HYDROCARBON_STAPLING = "hydrocarbon_stapling"
    DISULFIDE = "disulfide"
    BIARYL_BISALKYLATION = "biaryl_bisalkylation"
    AZA_PEPTIDE = "aza_peptide"
    RETRO_INVERSO = "retro_inverso"
    CHARGE_HYBRIDS = "charge_hybrids"


AA1_TO_3 = {
    "A": "Ala",
    "C": "Cys",
    "D": "Asp",
    "E": "Glu",
    "F": "Phe",
    "G": "Gly",
    "H": "His",
    "I": "Ile",
    "K": "Lys",
    "L": "Leu",
    "M": "Met",
    "N": "Asn",
    "P": "Pro",
    "Q": "Gln",
    "R": "Arg",
    "S": "Ser",
    "T": "Thr",
    "V": "Val",
    "W": "Trp",
    "Y": "Tyr",
}

AA3_TO_1 = {name.upper(): letter for letter, name in AA1_TO_3.items()}


class Residue(FrozenModel):
    index: int = Field(ge=1)
    letter: str
    annotation: str | None = None

    @property
    def three_letter(self) -> str | None:
        return AA1_TO_3.get(self.letter)

    @property
    def token(self) -> str:
        return f"{self.letter}{self.index}"


from route_agent.models.corpus import Provenance  # noqa: E402

SiteKind = Literal["position", "n_term", "c_term", "whole_sequence"]


class SiteAtom(FrozenModel):
    kind: SiteKind
    letter: str | None = None
    index: int | None = None
    token: str

    @model_validator(mode="after")
    def kind_fields_must_match(self) -> SiteAtom:
        if self.kind == "position" and (self.letter is None or self.index is None):
            raise ValueError("position atoms require letter and index")
        return self


class ResolvedSite(FrozenModel):
    modification_ref: int
    requested_token: str
    atoms: tuple[SiteAtom, ...]


class SiteMapEntry(FrozenModel):
    requested: str
    resolved: str
    residue: str | None
    note: str | None = None


class SiteInvalidFinding(FrozenModel):
    severity: Literal["blocking"] = "blocking"
    kind: Literal["site_invalid"] = "site_invalid"
    description: str
    affected: tuple[str, ...]
    resolution: str | None = None
    provenance: tuple[Provenance, ...]


STANDARD_LETTERS = frozenset("ACDEFGHIKLMNPQRSTVWY")


class ModificationRequest(FrozenModel):
    family: ModificationFamily
    site: str
    detail: str | None = None


class DesignRequest(FrozenModel):
    request_id: str
    parent_name: str
    sequence: str
    parent_c_terminus: ParentCTerminus
    residue_annotations: dict[str, str] = Field(default_factory=dict)
    parent_features: tuple[str, ...] = ()
    modifications: tuple[ModificationRequest, ...]
    intent: str

    @field_validator("sequence")
    @classmethod
    def sequence_must_be_nonempty(cls, value: str) -> str:
        if not value:
            raise ValueError("sequence must not be empty")
        return value

    @field_validator("parent_features", mode="before")
    @classmethod
    def coerce_parent_features(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        return tuple(value)

    @field_validator("modifications", mode="before")
    @classmethod
    def coerce_modifications(cls, value: Any) -> Any:
        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def every_x_must_be_declared(self) -> DesignRequest:
        missing: list[str] = []
        for index, letter in enumerate(self.sequence, start=1):
            if letter == "X":
                key = f"X{index}"
                if key not in self.residue_annotations:
                    missing.append(key)
            elif letter not in STANDARD_LETTERS:
                raise ValueError(
                    f"sequence[{index}]={letter!r} is outside the standard "
                    "one-letter alphabet and is not X"
                )
        if missing:
            raise ValueError(
                "every X must be declared in residue_annotations; missing "
                + ", ".join(missing)
            )
        return self


from route_agent.models.validation import ValidationError  # noqa: E402


class IndexMapEntry(FrozenModel):
    parent_index: int = Field(ge=1)
    resolved_index: int = Field(ge=1)
    parent_letter: str
    resolved_letter: str


class SequenceResolution(FrozenModel):
    resolved_sequence: str
    resolved_annotations: dict[str, str]
    index_map: tuple[IndexMapEntry, ...]


class SpecialTarget(FrozenModel):
    letter: str | None
    annotation: str
    d_only: bool


class ResolutionResult(FrozenModel):
    resolution: SequenceResolution
    errors: tuple[ValidationError, ...]
