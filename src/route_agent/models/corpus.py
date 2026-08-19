from __future__ import annotations

from typing import Any, Literal

from pydantic import ConfigDict, Field, model_serializer, model_validator

from route_agent.models.frozen import FrozenModel


class Provenance(FrozenModel):
    kind: Literal["corpus", "inference", "external"]
    ref: str | None = Field(
        default=None,
        description=(
            "Required when kind is corpus. Workbook row id such as "
            "ApexChem_Synthesis_Reactions_by_AminoAcid:06_Lipidation:8. "
            "Do not put prose in this field."
        ),
    )
    refs: tuple[str, ...] | None = None
    source: str | None = None
    basis: str | None = Field(
        default=None,
        description="Required when kind is inference or external. Prose support.",
    )

    @model_validator(mode="before")
    @classmethod
    def coerce_kind_fields(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        kind = data.get("kind")
        ref = _nonempty_text(data.get("ref"))
        refs = _ref_list(data.get("refs"))
        basis = _nonempty_text(data.get("basis"))
        source = _nonempty_text(data.get("source"))
        if ref is not None and " " in ref and not _looks_like_corpus_ref(ref):
            basis = basis or ref
            ref = None
            data["basis"] = basis
            data.pop("ref", None)
        if kind == "corpus" and ref is None:
            if refs:
                data["ref"] = refs[0]
            elif basis is not None and _looks_like_corpus_ref(basis):
                data["ref"] = basis
                data["basis"] = None
            elif basis is not None:
                data["kind"] = "inference"
            elif source is not None:
                data["kind"] = "external"
                data["basis"] = (
                    data.get("basis") or "external source without corpus ref"
                )
            else:
                data["kind"] = "inference"
                data["basis"] = "corpus citation missing ref"
        if ref is not None:
            data["ref"] = ref
        if refs:
            data["refs"] = refs
        return data

    @model_validator(mode="after")
    def kind_fields_must_match_schema(self) -> Provenance:
        if self.kind == "corpus":
            return _coerce_corpus_after(self)
        if self.kind == "inference" and not self.basis:
            return self.model_copy(update={"basis": "inference citation missing basis"})
        if self.kind == "external" and (not self.source or not self.basis):
            if self.source:
                return self.model_copy(
                    update={"basis": self.basis or "external citation missing basis"}
                )
            if self.basis:
                return self.model_copy(update={"kind": "inference"})
            return self.model_copy(
                update={
                    "kind": "inference",
                    "basis": "external citation missing source",
                }
            )
        return self

    @model_serializer(mode="wrap")
    def dump_allowed_fields(self, _serializer: Any) -> dict[str, Any]:
        if self.kind == "corpus":
            return {"kind": "corpus", "ref": self.ref}
        if self.kind == "inference":
            payload: dict[str, Any] = {"kind": "inference", "basis": self.basis}
            if self.refs:
                payload["refs"] = list(self.refs)
            return payload
        return {"kind": "external", "source": self.source, "basis": self.basis}


def _nonempty_text(value: object) -> str | None:
    if isinstance(value, (list, tuple)):
        return _nonempty_text(value[0]) if value else None
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _ref_list(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        item = _nonempty_text(value)
        return (item,) if item else ()
    if not isinstance(value, (list, tuple)):
        return ()
    items = [_nonempty_text(item) for item in value]
    return tuple(item for item in items if item is not None)


def _looks_like_corpus_ref(value: str) -> bool:
    text = value.strip()
    if " " in text or "\n" in text:
        return False
    parts = text.split(":")
    return len(parts) >= 3 and parts[-1].isdigit()


def _coerce_corpus_after(item: Provenance) -> Provenance:
    ref = _nonempty_text(item.ref)
    if ref is not None and not _looks_like_corpus_ref(ref) and " " in ref:
        return item.model_copy(
            update={"kind": "inference", "ref": None, "basis": item.basis or ref}
        )
    if ref:
        return item
    refs = item.refs or ()
    if refs:
        return item.model_copy(update={"ref": refs[0]})
    basis = _nonempty_text(item.basis)
    if basis is not None and _looks_like_corpus_ref(basis):
        return item.model_copy(update={"ref": basis, "basis": None})
    if basis is not None:
        return item.model_copy(update={"kind": "inference", "ref": None})
    if item.source:
        return item.model_copy(
            update={
                "kind": "external",
                "ref": None,
                "basis": item.basis or "external source without corpus ref",
            }
        )
    return item.model_copy(
        update={
            "kind": "inference",
            "ref": None,
            "basis": "corpus citation missing ref",
        }
    )


def inference_provenance(basis: str, refs: tuple[str, ...] = ()) -> Provenance:
    return Provenance(kind="inference", basis=basis, refs=refs or None)


class CorpusModel(FrozenModel):
    model_config = ConfigDict(frozen=True, extra="ignore")


class CorpusCell(CorpusModel):
    column: str | None = None
    value: str | None = None


class CorpusExcerpt(CorpusModel):
    cells: tuple[CorpusCell, ...] = ()
    provenance: tuple[Provenance, ...] = ()
    ref_row: int | None = None
    source_excerpt: str | None = None


class CorpusExcerptRef(FrozenModel):
    ref: str
    ref_row: int | None = None
    source_excerpt: str = ""


class FamilyProcessView(CorpusModel):
    process_id: str | None = None
    name: str | None = None
    protecting_groups: tuple[object, ...] = ()
    caveats: tuple[CorpusExcerpt, ...] = ()
    conditions: tuple[CorpusExcerpt, ...] = ()
    constraints: tuple[CorpusExcerpt, ...] = ()
    reagents: tuple[CorpusExcerpt, ...] = ()
    requires: tuple[CorpusExcerpt, ...] = ()
    stage_hint: str | None = None
    building_blocks: tuple[str, ...] = ()


class FamilyProfileView(CorpusModel):
    sheet: str
    summary: str = ""
    processes: dict[str, FamilyProcessView] = Field(default_factory=dict)


class ExtractedFamiliesView(CorpusModel):
    schema_version: str
    source_workbook: str
    family_order: tuple[str, ...]
    families: dict[str, FamilyProfileView]

    @model_validator(mode="after")
    def family_order_must_cover_catalog(self) -> ExtractedFamiliesView:
        if len(self.family_order) != len(set(self.family_order)):
            raise ValueError("family_order must not contain duplicates")
        if set(self.family_order) != set(self.families):
            raise ValueError("family_order must cover exactly the catalog families")
        return self


from route_agent.models.request import ModificationFamily  # noqa: E402


class FamilyBinding(FrozenModel):
    modification_ref: int
    family: ModificationFamily
    sheet: str
    process_ids: tuple[str, ...]
    provenance: tuple[Provenance, ...]
    site: str | None = None  # Optional override; walker otherwise uses the request site


class TargetLookupResult(FrozenModel):
    available: bool
    peptide: str | None = None
    receptor_target: str | None = None
    receptor_class: str | None = None
    ligand_role: str | None = None
    invariant_windows: tuple[str, ...] = ()
    sar_precedents: tuple[str, ...] = ()
    reason: str | None = None

    @staticmethod
    def unavailable(peptide: str | None = None) -> TargetLookupResult:
        return TargetLookupResult(
            available=False, peptide=peptide, reason="workbook_unavailable"
        )
