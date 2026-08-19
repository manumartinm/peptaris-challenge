from __future__ import annotations

import re
from dataclasses import dataclass

from route_agent.models.request import AA1_TO_3, AA3_TO_1, SpecialTarget
from route_agent.parser.policy import DEFAULT_CHEMISTRY, ChemistryPolicy

ARROW_RE = re.compile(r"(?:[A-Za-z]{1,4}\d*)\s*->\s*([A-Za-z0-9\-]+)")
SUBSTITUTE_RE = re.compile(r"substitute\s+(D-[A-Za-z]{3,}|[A-Za-z]{3,})", re.IGNORECASE)
FMOC_RE = re.compile(
    r"Fmoc-([A-Za-z][A-Za-z0-9]*)(?:\([^)]+\))?(?:-OH)?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedSubstitution:
    target: SpecialTarget
    catalogued: bool
    raw: str


def parse_residue_substitution(
    detail: str | None,
    chemistry: ChemistryPolicy | None = None,
) -> ParsedSubstitution | None:
    if not detail:
        return None
    arrow = ARROW_RE.search(detail)
    if arrow:
        return residue_substitution_from_name(arrow.group(1), chemistry)
    substitute = SUBSTITUTE_RE.search(detail)
    if substitute:
        return residue_substitution_from_name(substitute.group(1), chemistry)
    fmoc = FMOC_RE.search(detail)
    if fmoc:
        return residue_substitution_from_name(fmoc.group(1), chemistry)
    return None


def residue_substitution_from_name(
    raw: str,
    chemistry: ChemistryPolicy | None = None,
) -> ParsedSubstitution:
    policy = chemistry or DEFAULT_CHEMISTRY
    residue_name = raw.strip()
    is_d_enantiomer_only = residue_name.upper().startswith("D-")
    residue_core = residue_name[2:] if is_d_enantiomer_only else residue_name
    normalized_name = residue_core.upper()
    if len(residue_core) == 1 and residue_core.upper() in AA1_TO_3:
        letter = residue_core.upper()
        annotation = f"D-{AA1_TO_3[letter]}" if is_d_enantiomer_only else residue_core
        return ParsedSubstitution(
            target=SpecialTarget(
                letter=letter, annotation=annotation, d_only=is_d_enantiomer_only
            ),
            catalogued=True,
            raw=residue_name,
        )
    if normalized_name in AA3_TO_1:
        letter = AA3_TO_1[normalized_name]
        annotation = (
            f"D-{AA1_TO_3[letter]}" if is_d_enantiomer_only else AA1_TO_3[letter]
        )
        return ParsedSubstitution(
            target=SpecialTarget(
                letter=letter, annotation=annotation, d_only=is_d_enantiomer_only
            ),
            catalogued=True,
            raw=residue_name,
        )
    if normalized_name in policy.nonstandard:
        return ParsedSubstitution(
            target=SpecialTarget(
                letter=None,
                annotation=policy.nonstandard[normalized_name],
                d_only=False,
            ),
            catalogued=True,
            raw=residue_name,
        )
    if is_d_enantiomer_only:
        d_annotation = f"D-{residue_core[:1].upper()}{residue_core[1:].lower()}"
        return ParsedSubstitution(
            target=SpecialTarget(letter=None, annotation=d_annotation, d_only=True),
            catalogued=False,
            raw=residue_name,
        )
    return ParsedSubstitution(
        target=SpecialTarget(letter=None, annotation=residue_name, d_only=False),
        catalogued=False,
        raw=residue_name,
    )


def substitution_is_catalogued(
    detail: str | None,
    chemistry: ChemistryPolicy | None = None,
) -> bool:
    parsed = parse_residue_substitution(detail, chemistry)
    return parsed is not None and parsed.catalogued
