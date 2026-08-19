from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from route_agent.models.molecular import (
    Bond,
    MolecularRecipe,
    ProductFragment,
    TerminusKind,
)
from route_agent.parser.substitutions import substitution_is_catalogued

_LACTAM_RE = re.compile(
    r"lactam\s+([A-Za-z]\d+)\s*-\s*([A-Za-z]\d+)",
    re.IGNORECASE,
)
_PAIR_RE = re.compile(r"([A-Za-z]\d+)\s*-\s*([A-Za-z]\d+)")
_TOKEN_RE = re.compile(r"[A-Za-z]\d+")
_PRODUCT_KEYS = {
    "permanent_connectivity",
    "product_fragments",
    "residue_overrides",
    "n_methyl_sites",
    "termini",
    "resolved_sequence",
    "residue_annotations",
    "product_unknowns",
}


@dataclass
class ProductState:
    sequence: str
    annotations: dict[str, str]
    n_terminus: TerminusKind = "free"
    c_terminus: TerminusKind = "acid"
    bonds: list[Bond] = field(default_factory=list)
    fragments: list[ProductFragment] = field(default_factory=list)
    residue_overrides: dict[str, str] = field(default_factory=dict)
    n_methyl_sites: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def build_parent_product_state(
        cls,
        *,
        sequence: str,
        annotations: dict[str, str],
        parent_c_terminus: str,
        parent_features: tuple[str, ...] | list[str],
    ) -> ProductState:
        state = cls(
            sequence=sequence,
            annotations=dict(annotations),
            c_terminus=_c_terminus_from_parent(parent_c_terminus),
        )
        for feature in parent_features:
            state._apply_parent_feature(str(feature))
        return state

    @classmethod
    def from_dict(cls, output: dict[str, Any]) -> ProductState:
        termini = dict(output.get("termini") or {})
        return cls(
            sequence=str(output.get("resolved_sequence") or ""),
            annotations=dict(output.get("residue_annotations") or {}),
            n_terminus=_as_terminus(termini.get("n"), default="free"),
            c_terminus=_as_terminus(termini.get("c"), default="acid"),
            bonds=[
                Bond.model_validate(item)
                for item in output.get("permanent_connectivity") or ()
            ],
            fragments=[
                ProductFragment.model_validate(item)
                for item in output.get("product_fragments") or ()
            ],
            residue_overrides=dict(output.get("residue_overrides") or {}),
            n_methyl_sites=list(output.get("n_methyl_sites") or ()),
            unknowns=list(output.get("product_unknowns") or ()),
            extra={
                key: value for key, value in output.items() if key not in _PRODUCT_KEYS
            },
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.extra,
            "permanent_connectivity": [
                bond.model_dump(mode="json") for bond in self.bonds
            ],
            "product_fragments": [
                fragment.model_dump(mode="json") for fragment in self.fragments
            ],
            "residue_overrides": dict(self.residue_overrides),
            "n_methyl_sites": list(self.n_methyl_sites),
            "termini": {"n": self.n_terminus, "c": self.c_terminus},
            "resolved_sequence": self.sequence,
            "residue_annotations": dict(self.annotations),
            "product_unknowns": list(self.unknowns),
        }

    def apply_candidate_to_state(
        self,
        *,
        family: str,
        site: str,
        process: str,
        detail: str | None,
    ) -> ProductState:
        child = ProductState(
            sequence=self.sequence,
            annotations=dict(self.annotations),
            n_terminus=self.n_terminus,
            c_terminus=self.c_terminus,
            bonds=list(self.bonds),
            fragments=list(self.fragments),
            residue_overrides=dict(self.residue_overrides),
            n_methyl_sites=list(self.n_methyl_sites),
            unknowns=list(self.unknowns),
            extra=dict(self.extra),
        )
        dispatch: dict[str, Callable[[], None]] = {
            "n_term_acetylation": child._apply_n_term_acetylation,
            "c_term_amidation": child._apply_c_term_amidation,
            "n_methylation": lambda: child.n_methyl_sites.append(site),
            "lipidation": lambda: child._append_conjugate_chain(
                site, _lipidation_chain(detail)
            ),
            "pegylation": lambda: child._apply_pegylation(site, detail),
            "hydrocarbon_stapling": lambda: child._apply_hydrocarbon_stapling(site),
            "disulfide": lambda: child._apply_disulfide(site),
            "cyclization": lambda: child._apply_cyclization(process, site),
            "retro_inverso": lambda: child._apply_retro_inverso(process, detail),
            "special_residues": lambda: None,
            "spps_foundation": lambda: None,
            "charge_hybrids": lambda: child._apply_charge_hybrids(process, detail),
        }
        apply_family = dispatch.get(family)
        if apply_family is None:
            child.unknowns.append(f"unmapped_permanent_family:{family}:{process}")
        else:
            apply_family()
        return child

    def build_recipe(
        self,
        *,
        sequence: str | None = None,
        annotations: dict[str, str] | None = None,
    ) -> MolecularRecipe:
        return MolecularRecipe(
            sequence=str(sequence or self.sequence),
            annotations=dict(annotations or self.annotations),
            n_terminus=self.n_terminus,
            c_terminus=self.c_terminus,
            n_methyl_sites=tuple(self.n_methyl_sites),
            bonds=tuple(self.bonds),
            fragments=tuple(self.fragments),
            residue_overrides=dict(self.residue_overrides),
            unknowns=tuple(self.unknowns),
        )

    def _apply_parent_feature(self, feature: str) -> None:
        lowered = feature.lower()
        if "n-terminal acetyl" in lowered or "n-term acetyl" in lowered:
            self._apply_n_term_acetylation()
        if "disulfide" in lowered:
            self._apply_disulfide(feature)
        lactam = _LACTAM_RE.search(feature)
        if lactam:
            self._add_amide_side_chain(lactam.group(1), lactam.group(2))

    def _apply_n_term_acetylation(self) -> None:
        instance = self._next_instance_id("acetyl")
        self.fragments.append(
            ProductFragment(instance_id=instance, catalog_id="acetyl", site="N-term")
        )
        self.bonds.append(
            Bond(from_atom="N-term", to_fragment=instance, bond_type="amide")
        )
        self.n_terminus = "acetyl"

    def _apply_c_term_amidation(self) -> None:
        self.c_terminus = "amide"

    def _apply_pegylation(self, site: str, detail: str | None) -> None:
        catalog_id = _peg_catalog_id(detail, site)
        if site in {"N-term", "N-terminal"}:
            instance = self._next_instance_id(catalog_id)
            self.fragments.append(
                ProductFragment(
                    instance_id=instance, catalog_id=catalog_id, site="N-term"
                )
            )
            self.bonds.append(
                Bond(from_atom="N-term", to_fragment=instance, bond_type="amide")
            )
            self.n_terminus = "peg4" if catalog_id == "peg4" else "peg8"
            return
        self._append_conjugate_chain(site, (catalog_id,))

    def _apply_hydrocarbon_stapling(self, site: str) -> None:
        tokens = _site_tokens(site)
        if len(tokens) < 2:
            self.unknowns.append(f"unparsed_staple_site:{site}")
            return
        left, right = tokens[0], tokens[1]
        self.residue_overrides[left] = "s5"
        self.residue_overrides[right] = "s5"
        self.bonds.append(
            Bond(from_atom=f"{left}.S", to_fragment=f"{right}.S", bond_type="olefin")
        )

    def _apply_disulfide(self, site: str) -> None:
        pairs = _PAIR_RE.findall(site)
        for left, right in pairs:
            self.bonds.append(
                Bond(
                    from_atom=f"{left}.{_side_chain_port(left)}",
                    to_fragment=f"{right}.{_side_chain_port(right)}",
                    bond_type="disulfide",
                )
            )
        if not pairs:
            self.unknowns.append(f"unparsed_disulfide_site:{site}")

    def _apply_charge_hybrids(self, process: str, detail: str | None) -> None:
        if substitution_is_catalogued(detail):
            return
        self.unknowns.append(f"unmapped_permanent_family:charge_hybrids:{process}")

    def _apply_cyclization(self, process: str, site: str) -> None:
        if process == "head_to_tail_cyclization":
            self.bonds.append(
                Bond(from_atom="N-term", to_fragment="C-term", bond_type="amide")
            )
            return
        if process == "side_chain_lactam":
            tokens = _site_tokens(site)
            pairs = _PAIR_RE.findall(site)
            if pairs:
                left, right = pairs[0]
            elif len(tokens) >= 2:
                left, right = tokens[0], tokens[1]
            else:
                self.unknowns.append(f"unparsed_lactam_site:{site}")
                return
            self._add_amide_side_chain(left, right)
            return
        self.unknowns.append(f"unknown_cyclization_process:{process}")

    def _apply_retro_inverso(
        self, process: str = "", detail: str | None = None
    ) -> None:
        haystack = f"{process} {detail or ''}".lower()
        if (
            "partial" in haystack
            or "end-capped" in haystack
            or "end capped" in haystack
        ):
            return
        self._strip_n_terminal_caps()
        self.n_terminus = "malonyl"
        self.c_terminus = "gem_diamino"
        instance = self._next_instance_id("malonyl")
        self.fragments.append(
            ProductFragment(instance_id=instance, catalog_id="malonyl", site="N-term")
        )
        self.bonds.append(
            Bond(from_atom="N-term", to_fragment=instance, bond_type="amide")
        )

    def _strip_n_terminal_caps(self) -> None:
        drop_ids = {
            fragment.instance_id
            for fragment in self.fragments
            if fragment.site in {"N-term", "N-terminal"}
            or fragment.catalog_id in {"acetyl", "malonyl"}
        }
        self.fragments = [
            fragment
            for fragment in self.fragments
            if fragment.instance_id not in drop_ids
        ]
        self.bonds = [
            bond
            for bond in self.bonds
            if bond.from_atom not in {"N-term", "N-terminal"}
            and bond.to_fragment not in drop_ids
        ]

    def _add_amide_side_chain(self, left: str, right: str) -> None:
        self.bonds.append(
            Bond(
                from_atom=f"{left}.{_side_chain_port(left)}",
                to_fragment=f"{right}.{_side_chain_port(right)}",
                bond_type="amide",
            )
        )

    def _append_conjugate_chain(self, site: str, catalog_ids: tuple[str, ...]) -> None:
        previous = f"{site}.{_side_chain_port(site)}"
        for catalog_id in catalog_ids:
            instance = self._next_instance_id(catalog_id)
            self.fragments.append(
                ProductFragment(instance_id=instance, catalog_id=catalog_id, site=site)
            )
            self.bonds.append(
                Bond(from_atom=previous, to_fragment=instance, bond_type="amide")
            )
            previous = f"{instance}.N"

    def _next_instance_id(self, catalog_id: str) -> str:
        count = sum(
            1 for fragment in self.fragments if fragment.catalog_id == catalog_id
        )
        return f"{catalog_id}:{count + 1}"


def build_parent_product_state(
    *,
    sequence: str,
    annotations: dict[str, str],
    parent_c_terminus: str,
    parent_features: tuple[str, ...] | list[str],
) -> dict[str, Any]:
    return ProductState.build_parent_product_state(
        sequence=sequence,
        annotations=annotations,
        parent_c_terminus=parent_c_terminus,
        parent_features=parent_features,
    ).to_dict()


def apply_candidate_to_state(
    output: dict[str, Any],
    *,
    family: str,
    site: str,
    process: str,
    detail: str | None,
) -> dict[str, Any]:
    return (
        ProductState.from_dict(output)
        .apply_candidate_to_state(
            family=family,
            site=site,
            process=process,
            detail=detail,
        )
        .to_dict()
    )


def build_recipe(
    output: dict[str, Any],
    *,
    sequence: str | None = None,
    annotations: dict[str, str] | None = None,
) -> MolecularRecipe:
    return ProductState.from_dict(output).build_recipe(
        sequence=sequence,
        annotations=annotations,
    )


def _c_terminus_from_parent(parent_c_terminus: str) -> TerminusKind:
    if parent_c_terminus == "amide":
        return "amide"
    if parent_c_terminus == "alcohol":
        return "alcohol"
    return "acid"


def _as_terminus(value: object, *, default: TerminusKind) -> TerminusKind:
    text = str(value or default)
    mapping: dict[str, TerminusKind] = {
        "free": "free",
        "acetyl": "acetyl",
        "amide": "amide",
        "acid": "acid",
        "alcohol": "alcohol",
        "malonyl": "malonyl",
        "gem_diamino": "gem_diamino",
        "peg4": "peg4",
        "peg8": "peg8",
        "free_acid": "acid",
    }
    return mapping.get(text, default)


def _lipidation_chain(detail: str | None) -> tuple[str, ...]:
    text = (detail or "").lower()
    compact = text.replace(" ", "")
    if "aeea" in text and "gglu" in text:
        if "2xaeea" in compact or "2x aeea" in text:
            count = 2
        else:
            count = max(text.count("aeea"), 1)
        aeea = tuple("aeea" for _ in range(count))
        lipid = "c18_diacid" if "c18" in text else "c16"
        return (*aeea, "gglu", lipid)
    if "gglu" in text or "γglu" in text or "gamma" in text:
        lipid = "c18_diacid" if "c18" in text else "c16"
        return ("gglu", lipid)
    if "c18" in text:
        return ("c18_diacid",)
    return ("c16",)


def _peg_catalog_id(detail: str | None, site: str) -> str:
    text = (detail or "").lower()
    if "peg8" in text:
        return "peg8"
    if "peg4" in text:
        return "peg4"
    return "peg8" if site in {"N-term", "N-terminal"} else "peg4"


def _site_tokens(site: str) -> tuple[str, ...]:
    return tuple(_TOKEN_RE.findall(site))


_SIDE_CHAIN_PORTS = {
    "C": "SG",
    "K": "NZ",
    "D": "CG",
    "E": "CD",
    "S": "OG",
    "T": "OG",
    "Y": "OH",
    "W": "NE",
}


def _side_chain_port(token: str) -> str:
    letter = token[0].upper() if token else ""
    return _SIDE_CHAIN_PORTS.get(letter, "S")
