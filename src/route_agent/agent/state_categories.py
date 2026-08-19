"""Semantic ledger categories used by the compatibility cache.

Categories abstract chemically relevant facts so equivalent protecting-group
families can share a cache entry. The cache key still includes the candidate
site so findings bound to one residue are never replayed at another.
"""

from __future__ import annotations

from typing import Any, Literal

StateCategory = Literal[
    "Fmoc_must_survive",
    "mild_acid_labile_side_chains_present",
    "hydrazine_labile_present",
    "alloc_allyl_present",
    "strong_acid_labile_present",
    "free_amines_exposed",
    "metal_catalyst_used",
    "disulfide_in_topology",
    "amide_in_topology",
    "pending_branch_target_present",
    "n_term_capped",
    "c_term_amide",
    "n_methyl_present",
    "product_unknowns_present",
]

_MILD_ACID = frozenset(
    {"mtt", "trt", "mmt", "2-cl-trt", "2cltrt", "o-2-phipr", "2-phipr"}
)
_HYDRAZINE = frozenset({"ivdde", "dde"})
_ALLOC = frozenset({"alloc", "oall", "allyl"})
_STRONG_ACID = frozenset({"boc", "tbu", "otbu", "pbf", "tbutyl"})
_N_TERM_CAPS = frozenset({"acetyl", "ac", "pyroglutamate", "pyroglu", "capped"})
_C_TERM_AMIDE = frozenset({"amide", "nh2", "c_term_amide"})


def derive_state_categories(state_payload: dict[str, Any]) -> frozenset[str]:
    """Map a ledger-like dict to coarse chemical categories."""
    present: set[str] = set()
    protected = state_payload.get("protected") or {}
    if isinstance(protected, dict):
        for label in protected.values():
            if label is None:
                continue
            family = classify_protecting_group(str(label))
            if family == "fmoc":
                present.add("Fmoc_must_survive")
            elif family == "mild_acid":
                present.add("mild_acid_labile_side_chains_present")
            elif family == "hydrazine":
                present.add("hydrazine_labile_present")
            elif family == "alloc":
                present.add("alloc_allyl_present")
            elif family == "strong_acid":
                present.add("strong_acid_labile_present")
            elif family == "pending":
                present.add("pending_branch_target_present")
            else:
                present.add(f"pg:{_normalize(str(label))}")
    amines = state_payload.get("free_amines") or {}
    if isinstance(amines, dict) and any(amines.values()):
        present.add("free_amines_exposed")
    catalysts = state_payload.get("catalysts_used") or {}
    if isinstance(catalysts, dict) and any(catalysts.values()):
        present.add("metal_catalyst_used")
    termini = state_payload.get("termini") or {}
    if isinstance(termini, dict):
        n_term = _normalize(str(termini.get("n") or ""))
        c_term = _normalize(str(termini.get("c") or ""))
        if n_term in _N_TERM_CAPS:
            present.add("n_term_capped")
        elif n_term:
            present.add("Fmoc_must_survive")
        if c_term in _C_TERM_AMIDE:
            present.add("c_term_amide")
        elif c_term:
            present.add(f"c_term:{c_term}")
    if "Fmoc_must_survive" not in present and "n_term_capped" not in present:
        present.add("Fmoc_must_survive")
    history = state_payload.get("history") or []
    if isinstance(history, list):
        for item in history:
            if isinstance(item, dict) and item.get("process"):
                present.add(f"history:{item['process']}")
            elif item:
                present.add(f"history:{item}")
    bonds = state_payload.get("permanent_connectivity") or []
    if isinstance(bonds, list):
        for item in bonds:
            if not isinstance(item, dict):
                continue
            bond_type = _normalize(str(item.get("bond_type") or "bond"))
            present.add(f"{bond_type}_in_topology")
    fragments = state_payload.get("product_fragments") or []
    if isinstance(fragments, list):
        for item in fragments:
            if isinstance(item, dict):
                catalog = item.get("catalog_id") or item.get("instance_id")
                if catalog:
                    present.add(f"fragment:{catalog}")
            elif item:
                present.add(f"fragment:{item}")
    overrides = state_payload.get("residue_overrides") or {}
    if isinstance(overrides, dict):
        for site, label in overrides.items():
            if label is not None:
                present.add(f"override:{site}:{label}")
    if state_payload.get("n_methyl_sites"):
        present.add("n_methyl_present")
    if state_payload.get("product_unknowns"):
        present.add("product_unknowns_present")
    return frozenset(present)


def classify_protecting_group(label: str) -> str | None:
    token = _normalize(label)
    if token == "pending":
        return "pending"
    if token == "fmoc":
        return "fmoc"
    if token in _MILD_ACID:
        return "mild_acid"
    if token in _HYDRAZINE:
        return "hydrazine"
    if token in _ALLOC:
        return "alloc"
    if token in _STRONG_ACID:
        return "strong_acid"
    if token == "acm":
        return "acm"
    return None


def _normalize(value: str) -> str:
    return (
        value.strip()
        .lower()
        .replace("_", "")
        .replace(" ", "")
        .replace("(", "")
        .replace(")", "")
    )
