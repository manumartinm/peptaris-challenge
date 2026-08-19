from __future__ import annotations

import re
from collections.abc import Sequence

from route_agent.models.request import (
    AA1_TO_3,
    STANDARD_LETTERS,
    DesignRequest,
    IndexMapEntry,
    ModificationFamily,
    Residue,
    ResolutionResult,
    ResolvedSite,
    SequenceResolution,
)
from route_agent.models.validation import ErrorCode, SequenceValidation
from route_agent.parser.errors import ErrorFactory
from route_agent.parser.policy import DEFAULT_CHEMISTRY, ChemistryPolicy
from route_agent.parser.sites import sites_by_modification_ref
from route_agent.parser.substitutions import parse_residue_substitution

LETTER_TRANSFORM_FAMILIES = {
    ModificationFamily.SPECIAL_RESIDUES,
    ModificationFamily.CHARGE_HYBRIDS,
}


class SequenceValidator:
    def __init__(self, errors: ErrorFactory | None = None) -> None:
        self._errors = errors or ErrorFactory()

    def validate_parent_sequence(
        self, sequence: str, residue_annotations: dict[str, str]
    ) -> SequenceValidation:
        if not sequence:
            return SequenceValidation(
                residues=(),
                errors=(
                    self._errors.sequence_error(
                        code=ErrorCode.SEQUENCE_EMPTY,
                        field_path="sequence",
                        input_snapshot={"sequence": sequence},
                        expected="non-empty one-letter sequence",
                        got=sequence,
                        message="Sequence is empty.",
                    ),
                ),
            )

        residues: list[Residue] = []
        errors = []
        for index, letter in enumerate(sequence, start=1):
            if letter != "X" and letter not in STANDARD_LETTERS:
                errors.append(
                    self._errors.sequence_error(
                        code=ErrorCode.SEQUENCE_ALPHABET,
                        field_path="sequence",
                        input_snapshot={"index": index, "letter": letter},
                        expected="standard one-letter code or X",
                        got=letter,
                        message=(
                            f"Letter {letter!r} at 1-based index {index} "
                            "is not allowed."
                        ),
                    )
                )
            annotation_key = f"{letter}{index}"
            residues.append(
                Residue(
                    index=index,
                    letter=letter,
                    annotation=residue_annotations.get(annotation_key),
                )
            )
        return SequenceValidation(residues=tuple(residues), errors=tuple(errors))


class SequenceResolver:
    def __init__(
        self,
        errors: ErrorFactory | None = None,
        chemistry: ChemistryPolicy | None = None,
    ) -> None:
        self._errors = errors or ErrorFactory()
        self._chemistry = chemistry or DEFAULT_CHEMISTRY

    def apply_sequence_transforms(
        self,
        request: DesignRequest,
        residues: Sequence[Residue],
        sites: Sequence[ResolvedSite],
    ) -> ResolutionResult:
        letters = [residue.letter for residue in residues]
        annotations = dict(request.residue_annotations)
        errors = []
        by_ref = sites_by_modification_ref(sites)
        retro_parity = 0

        for index, modification in enumerate(request.modifications):
            site = by_ref.get(index)
            if site is None:
                continue
            if modification.family == ModificationFamily.RETRO_INVERSO:
                letters, annotations = self._apply_retro_inverso_transform(
                    letters, annotations
                )
                retro_parity += 1
                continue
            if modification.family not in LETTER_TRANSFORM_FAMILIES:
                continue
            parsed = parse_residue_substitution(modification.detail, self._chemistry)
            if parsed is None:
                if modification.family == ModificationFamily.SPECIAL_RESIDUES:
                    errors.append(
                        self._errors.sequence_transform_error(
                            modification_ref=index,
                            detail=modification.detail,
                            site=modification.site,
                            message=(
                                "special_residues detail does not name a letter-level "
                                "transform; leaving the parent letter unchanged."
                            ),
                        )
                    )
                continue
            if (
                modification.family == ModificationFamily.CHARGE_HYBRIDS
                and not parsed.catalogued
            ):
                errors.append(
                    self._errors.sequence_transform_error(
                        modification_ref=index,
                        detail=modification.detail,
                        site=modification.site,
                        message=(
                            "charge_hybrids names a residue that is not in the "
                            "nonstandard catalogue; leaving the parent letter "
                            "unchanged."
                        ),
                    )
                )
                continue
            target = parsed.target
            for atom in site.atoms:
                if atom.index is None:
                    continue
                position = atom.index - 1
                if target.d_only:
                    key = f"{letters[position]}{atom.index}"
                    annotations[key] = target.annotation
                elif target.letter is None:
                    letters[position] = "X"
                    annotations[f"X{atom.index}"] = target.annotation
                else:
                    letters[position] = target.letter

        index_map = tuple(
            IndexMapEntry(
                parent_index=residue.index,
                resolved_index=resolved_index,
                parent_letter=residue.letter,
                resolved_letter=letters[resolved_index - 1],
            )
            for residue, resolved_index in self._parent_to_resolved_pairs(
                residues, reversed_once=retro_parity % 2 == 1
            )
        )
        return ResolutionResult(
            resolution=SequenceResolution(
                resolved_sequence="".join(letters),
                resolved_annotations=annotations,
                index_map=index_map,
            ),
            errors=tuple(errors),
        )

    def _parent_to_resolved_pairs(
        self, residues: Sequence[Residue], *, reversed_once: bool
    ) -> list[tuple[Residue, int]]:
        length = len(residues)
        if reversed_once:
            return [(residue, length - residue.index + 1) for residue in residues]
        return [(residue, residue.index) for residue in residues]

    def _apply_retro_inverso_transform(
        self, letters: list[str], annotations: dict[str, str]
    ) -> tuple[list[str], dict[str, str]]:
        length = len(letters)
        reversed_letters = list(reversed(letters))
        remapped: dict[str, str] = {}
        for key, value in annotations.items():
            remapped[self._remap_annotation_key(key, length)] = value
        for index, letter in enumerate(reversed_letters, start=1):
            three_letter = AA1_TO_3.get(letter)
            if three_letter is not None:
                remapped[f"{letter}{index}"] = f"D-{three_letter}"
        if "N-term" in annotations:
            remapped["C-term"] = annotations["N-term"]
        remapped.pop("N-term", None)
        return reversed_letters, remapped

    def _remap_annotation_key(self, key: str, length: int) -> str:
        match = re.fullmatch(r"([A-Za-z]|X)(\d+)", key)
        if match is None:
            return key
        letter, index_text = match.group(1), match.group(2)
        parent_index = int(index_text)
        resolved_index = length - parent_index + 1
        return f"{letter}{resolved_index}"
