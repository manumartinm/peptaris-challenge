from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import model_validator

from route_agent.models.frozen import FrozenModel


class ValidationCheck(StrEnum):
    VALIDATE_SEQUENCE = "validate_sequence"
    VALIDATE_MODIFICATION_SITES = "validate_modification_sites"
    PARENT_FEATURES = "parent_features"
    RESOLVE_FAMILY = "resolve_family"
    RESOLVE_SEQUENCE = "resolve_sequence"
    ASSIGN_PROTECTING_GROUPS = "assign_protecting_groups"
    SELECT_RESIN = "select_resin"


ValidationStage = ValidationCheck


class ErrorCode(StrEnum):
    SEQUENCE_EMPTY = "SEQUENCE_EMPTY"
    SEQUENCE_ALPHABET = "SEQUENCE_ALPHABET"
    SEQUENCE_TRANSFORM_AMBIGUOUS = "SEQUENCE_TRANSFORM_AMBIGUOUS"
    SITE_MALFORMED = "SITE_MALFORMED"
    SITE_OUT_OF_RANGE = "SITE_OUT_OF_RANGE"
    SITE_LETTER_MISMATCH = "SITE_LETTER_MISMATCH"
    STRUCTURER_FAILED = "STRUCTURER_FAILED"
    STRUCTURER_INVALID_OUTPUT = "STRUCTURER_INVALID_OUTPUT"
    FAMILY_UNBOUND = "FAMILY_UNBOUND"
    PROTECTING_GROUP_UNKNOWN = "PROTECTING_GROUP_UNKNOWN"
    RESIN_UNSUPPORTED_TERMINUS = "RESIN_UNSUPPORTED_TERMINUS"


ConflictKind = Literal["site_invalid"]
CauseType = Literal[
    "site_invalid",
    "sequence_invalid",
    "sequence_transform_ambiguous",
    "family_unbound",
    "protecting_group_unknown",
    "resin_unsupported",
    "structurer_failed",
]


class ValidationError(FrozenModel):
    id: str
    code: ErrorCode
    check: ValidationCheck
    stage: ValidationStage
    field_path: str
    input_snapshot: dict[str, Any]
    expected: str
    got: str
    ref: str | None
    modification_ref: int | None
    message: str
    cause_type: str
    retryable: bool
    conflict_kind: ConflictKind | None = None


from route_agent.models.agent import LLMCall  # noqa: E402
from route_agent.models.corpus import Provenance  # noqa: E402
from route_agent.models.request import (  # noqa: E402
    ParentCTerminus,
    Residue,
    ResolvedSite,
    SiteInvalidFinding,
    SiteMapEntry,
)


class SequenceValidation(FrozenModel):
    residues: tuple[Residue, ...]
    errors: tuple[ValidationError, ...]


class SiteValidation(FrozenModel):
    sites_resolved: tuple[ResolvedSite, ...]
    site_map: tuple[SiteMapEntry, ...]
    errors: tuple[ValidationError, ...]
    conflicts: tuple[SiteInvalidFinding, ...]


class StructuredSpan(FrozenModel):
    text: str
    start: int
    end: int

    @model_validator(mode="after")
    def end_must_follow_start(self) -> StructuredSpan:
        if self.end < self.start:
            raise ValueError("span end must be >= start")
        return self


class StructuredFeature(FrozenModel):
    source_field: str
    raw_text: str
    classification: str
    site_token: str | None = None
    evidence: tuple[StructuredSpan, ...] = ()
    unmapped: bool = False


class StructuredFreeText(FrozenModel):
    features: tuple[StructuredFeature, ...]
    occupancy: tuple[str, ...]
    route_seed: tuple[str, ...]
    unmapped_spans: tuple[StructuredSpan, ...] = ()


class StructuringResult(FrozenModel):
    text: StructuredFreeText
    errors: tuple[ValidationError, ...]
    llm_call: LLMCall | None


class ProtectionLedger(FrozenModel):
    protected: dict[str, str]
    provenance: tuple[Provenance, ...]
    policy_version: str


class ProtectionResult(FrozenModel):
    ledger: ProtectionLedger
    errors: tuple[ValidationError, ...]


class ResinSelection(FrozenModel):
    resin: str
    operation: str
    cyclization_anchor_requested: bool
    amidation_requested: bool
    parent_c_terminus: ParentCTerminus
    provenance: tuple[Provenance, ...]
    route_step: dict[str, str]


class ResinResult(FrozenModel):
    selection: ResinSelection | None
    errors: tuple[ValidationError, ...]
