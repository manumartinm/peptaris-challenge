from __future__ import annotations

import re
from collections.abc import Sequence

from route_agent.models.corpus import Provenance
from route_agent.models.request import (
    AA1_TO_3,
    DesignRequest,
    IndexMapEntry,
    Residue,
    ResolvedSite,
    SiteAtom,
    SiteInvalidFinding,
    SiteMapEntry,
)
from route_agent.models.validation import ErrorCode, SiteValidation, ValidationError
from route_agent.parser.errors import ErrorFactory

KEYWORD_N_TERM = "n-term"
KEYWORD_C_TERM = "c-term"
KEYWORD_BOTH = "both termini"
KEYWORD_WHOLE = "whole sequence"
POSITION_RE = re.compile(r"^([A-Z])(\d+)$")
POSITION_TOKEN_RE = re.compile(r"[A-Z]\d+")
RANGE_RE = re.compile(r"^([A-Z])(\d+)-([A-Z])(\d+)$")
PRODUCT_FRAME_RE = re.compile(
    r"position\s+(\d+)\s+of\s+(?:the\s+)?(?:retro[-\s]?inverso\s+)?(?:ri\s+)?product",
    re.IGNORECASE,
)


def sites_by_modification_ref(
    sites: Sequence[ResolvedSite],
) -> dict[int, ResolvedSite]:
    return {site.modification_ref: site for site in sites}


def resolve_site_token(site: ResolvedSite) -> str:
    """Keep requested grammar; rewrite position tokens with remapped atoms.

    A comma-separated staple (`V21,R25`) stays one bridge token. `site_map`
    expands that token to one entry per endpoint for reporting, but the
    walker still applies a single modification.
    """
    if not site.atoms:
        return site.requested_token
    position_atoms = [atom for atom in site.atoms if atom.kind == "position"]
    if not position_atoms:
        return site.requested_token
    matches = list(POSITION_TOKEN_RE.finditer(site.requested_token))
    if len(matches) != len(position_atoms):
        return site.requested_token
    rewritten = site.requested_token
    for match, atom in zip(reversed(matches), reversed(position_atoms), strict=True):
        rewritten = rewritten[: match.start()] + atom.token + rewritten[match.end() :]
    return rewritten


class SiteValidator:
    def __init__(self, errors: ErrorFactory | None = None) -> None:
        self._errors = errors or ErrorFactory()

    def validate_modification_sites(
        self,
        request: DesignRequest,
        residues: Sequence[Residue],
        sequence_length: int | None = None,
    ) -> SiteValidation:
        by_index = {residue.index: residue for residue in residues}
        sequence_length = (
            len(request.sequence) if sequence_length is None else sequence_length
        )
        sites: list[ResolvedSite] = []
        site_map: list[SiteMapEntry] = []
        errors: list[ValidationError] = []
        conflicts: list[SiteInvalidFinding] = []

        for modification_ref, modification in enumerate(request.modifications):
            atoms, token_errors = self._parse_site_token(
                modification.site,
                modification_ref=modification_ref,
                by_index=by_index,
                sequence_length=sequence_length,
            )
            errors.extend(token_errors)
            if token_errors:
                conflicts.append(
                    SiteInvalidFinding(
                        description=token_errors[0].message,
                        affected=(modification.site,),
                        provenance=(
                            Provenance(
                                kind="inference",
                                basis="Site grammar and 1-based parent sequence check",
                            ),
                        ),
                    )
                )
                continue
            sites.append(
                ResolvedSite(
                    modification_ref=modification_ref,
                    requested_token=modification.site,
                    atoms=tuple(atoms),
                )
            )
            site_map.extend(
                self._build_remapped_site_map_entries(modification.site, atoms, atoms)
            )

        return SiteValidation(
            sites_resolved=tuple(sites),
            site_map=tuple(site_map),
            errors=tuple(errors),
            conflicts=tuple(conflicts),
        )

    def remap_sites_to_resolved_sequence(
        self,
        validation: SiteValidation,
        index_map: Sequence[IndexMapEntry],
    ) -> SiteValidation:
        by_parent_index = {entry.parent_index: entry for entry in index_map}
        remapped_sites: list[ResolvedSite] = []
        remapped_map: list[SiteMapEntry] = []
        for site in validation.sites_resolved:
            remapped_atoms = tuple(
                self._remap_site_atom_through_index_map(atom, by_parent_index)
                for atom in site.atoms
            )
            remapped_sites.append(
                ResolvedSite(
                    modification_ref=site.modification_ref,
                    requested_token=site.requested_token,
                    atoms=remapped_atoms,
                )
            )
            remapped_map.extend(
                self._build_remapped_site_map_entries(
                    site.requested_token, site.atoms, remapped_atoms
                )
            )
        return SiteValidation(
            sites_resolved=tuple(remapped_sites),
            site_map=tuple(remapped_map),
            errors=validation.errors,
            conflicts=validation.conflicts,
        )

    def flag_conflicting_site_frames(
        self,
        request: DesignRequest,
        validation: SiteValidation,
        resolved_sequence: str,
    ) -> SiteValidation:
        by_ref = sites_by_modification_ref(validation.sites_resolved)
        extra_errors: list[ValidationError] = []
        extra_conflicts: list[SiteInvalidFinding] = []
        for modification_ref, modification in enumerate(request.modifications):
            product_index = _product_frame_index(modification.detail)
            if product_index is None:
                continue
            site = by_ref.get(modification_ref)
            if site is None:
                continue
            remapped = [
                atom
                for atom in site.atoms
                if atom.kind == "position" and atom.index is not None
            ]
            if not remapped:
                continue
            if any(atom.index == product_index for atom in remapped):
                continue
            remapped_tokens = ", ".join(atom.token for atom in remapped)
            extra_errors.append(
                self._errors.site_error(
                    code=ErrorCode.SITE_LETTER_MISMATCH,
                    token=modification.site,
                    modification_ref=modification_ref,
                    expected=(
                        f"site and detail to name the same residue after remap "
                        f"({remapped_tokens})"
                    ),
                    message=(
                        f"Site {modification.site} remapped to {remapped_tokens} "
                        f"but detail names position {product_index} of the product."
                    ),
                    sequence_length=len(resolved_sequence),
                    extra={
                        "detail_index": product_index,
                        "remapped": remapped_tokens,
                    },
                )
            )
            extra_conflicts.append(
                SiteInvalidFinding(
                    description=extra_errors[-1].message,
                    affected=(modification.site, f"position {product_index}"),
                    provenance=(
                        Provenance(
                            kind="inference",
                            basis=(
                                "Site token and detail use different coordinate "
                                "frames after sequence transform"
                            ),
                        ),
                    ),
                )
            )
        if not extra_errors:
            return validation
        return SiteValidation(
            sites_resolved=validation.sites_resolved,
            site_map=validation.site_map,
            errors=(*validation.errors, *extra_errors),
            conflicts=(*validation.conflicts, *extra_conflicts),
        )

    def _parse_site_token(
        self,
        raw_token: str,
        *,
        modification_ref: int,
        by_index: dict[int, Residue],
        sequence_length: int,
    ) -> tuple[list[SiteAtom], list[ValidationError]]:
        normalized = " ".join(raw_token.split()).lower()
        if normalized == KEYWORD_N_TERM:
            return [SiteAtom(kind="n_term", token="N-term")], []
        if normalized == KEYWORD_C_TERM:
            return [SiteAtom(kind="c_term", token="C-term")], []
        if normalized == KEYWORD_BOTH:
            return [
                SiteAtom(kind="n_term", token="N-term"),
                SiteAtom(kind="c_term", token="C-term"),
            ], []
        if normalized == KEYWORD_WHOLE:
            return [SiteAtom(kind="whole_sequence", token="whole sequence")], []

        parts = [part.strip() for part in raw_token.split(",") if part.strip()]
        if not parts:
            return [], [
                self._errors.site_error(
                    code=ErrorCode.SITE_MALFORMED,
                    token=raw_token,
                    modification_ref=modification_ref,
                    expected="position, range, or keyword site",
                    message=f"Site token {raw_token!r} is empty after splitting.",
                    sequence_length=sequence_length,
                )
            ]

        atoms: list[SiteAtom] = []
        errors: list[ValidationError] = []
        for part in parts:
            compact = part.replace(" ", "")
            range_match = RANGE_RE.fullmatch(compact)
            position_match = POSITION_RE.fullmatch(compact)
            if range_match:
                left_letter, left_index, right_letter, right_index = (
                    range_match.groups()
                )
                for letter, index_text in (
                    (left_letter, left_index),
                    (right_letter, right_index),
                ):
                    atom, error = self._resolve_site_atom(
                        letter,
                        int(index_text),
                        raw_token=raw_token,
                        modification_ref=modification_ref,
                        by_index=by_index,
                        sequence_length=sequence_length,
                    )
                    if error is not None:
                        errors.append(error)
                    elif atom is not None:
                        atoms.append(atom)
            elif position_match:
                letter, index_text = position_match.groups()
                atom, error = self._resolve_site_atom(
                    letter,
                    int(index_text),
                    raw_token=raw_token,
                    modification_ref=modification_ref,
                    by_index=by_index,
                    sequence_length=sequence_length,
                )
                if error is not None:
                    errors.append(error)
                elif atom is not None:
                    atoms.append(atom)
            else:
                errors.append(
                    self._errors.site_error(
                        code=ErrorCode.SITE_MALFORMED,
                        token=raw_token,
                        modification_ref=modification_ref,
                        expected=(
                            "K12, C2-C7, N-term, C-term, both termini, "
                            "or whole sequence"
                        ),
                        message=f"Site fragment {part!r} is not valid site grammar.",
                        sequence_length=sequence_length,
                    )
                )
        return atoms, errors

    def _resolve_site_atom(
        self,
        letter: str,
        index: int,
        *,
        raw_token: str,
        modification_ref: int,
        by_index: dict[int, Residue],
        sequence_length: int,
    ) -> tuple[SiteAtom | None, ValidationError | None]:
        residue = by_index.get(index)
        if residue is None:
            if index > sequence_length:
                return None, self._errors.site_error(
                    code=ErrorCode.SITE_OUT_OF_RANGE,
                    token=raw_token,
                    modification_ref=modification_ref,
                    expected=f"1-based index within sequence length {sequence_length}",
                    message=f"Site {letter}{index} is outside the parent sequence.",
                    sequence_length=sequence_length,
                    extra={"letter": letter, "index": index},
                )
            return None, self._errors.site_error(
                code=ErrorCode.SITE_OUT_OF_RANGE,
                token=raw_token,
                modification_ref=modification_ref,
                expected=f"residue present at 1-based index {index}",
                message=f"Site {letter}{index} has no residue at this index.",
                sequence_length=sequence_length,
                extra={"letter": letter, "index": index},
            )
        if residue.letter != letter:
            return None, self._errors.site_error(
                code=ErrorCode.SITE_LETTER_MISMATCH,
                token=raw_token,
                modification_ref=modification_ref,
                expected=f"{residue.letter}{index}",
                message=(
                    f"Site {letter}{index} does not match parent residue "
                    f"{residue.letter}{index}."
                ),
                sequence_length=sequence_length,
                extra={"letter": letter, "index": index, "actual": residue.letter},
            )
        return (
            SiteAtom(
                kind="position",
                letter=letter,
                index=index,
                token=f"{letter}{index}",
            ),
            None,
        )

    def _remap_site_atom_through_index_map(
        self, atom: SiteAtom, by_parent_index: dict[int, IndexMapEntry]
    ) -> SiteAtom:
        if atom.kind != "position" or atom.index is None:
            return atom
        mapping = by_parent_index.get(atom.index)
        if mapping is None:
            return atom
        return SiteAtom(
            kind="position",
            letter=mapping.resolved_letter,
            index=mapping.resolved_index,
            token=f"{mapping.resolved_letter}{mapping.resolved_index}",
        )

    def _build_remapped_site_map_entries(
        self,
        requested_token: str,
        parent_atoms: Sequence[SiteAtom],
        remapped_atoms: Sequence[SiteAtom],
    ) -> list[SiteMapEntry]:
        entries: list[SiteMapEntry] = []
        for parent_atom, remapped_atom in zip(
            parent_atoms, remapped_atoms, strict=True
        ):
            if remapped_atom.kind == "position":
                if remapped_atom.letter is None:
                    raise ValueError("remapped position atom is missing a letter")
                note = None
                if parent_atom.token != remapped_atom.token:
                    note = (
                        f"parent {parent_atom.token} remapped to {remapped_atom.token}"
                    )
                entries.append(
                    SiteMapEntry(
                        requested=requested_token,
                        resolved=remapped_atom.token,
                        residue=AA1_TO_3.get(remapped_atom.letter),
                        note=note,
                    )
                )
            else:
                entries.append(
                    SiteMapEntry(
                        requested=requested_token,
                        resolved=remapped_atom.token,
                        residue=None,
                        note=None,
                    )
                )
        return entries


def _product_frame_index(detail: str | None) -> int | None:
    if not detail:
        return None
    match = PRODUCT_FRAME_RE.search(detail)
    if match is None:
        return None
    return int(match.group(1))
