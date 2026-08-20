"""Rebuild protecting-group occupancy from census, prior work, and the candidate."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from route_agent.models.agent import AgentCandidate
from route_agent.models.corpus import Provenance
from route_agent.models.request import DesignRequest, Residue, ResolvedSite
from route_agent.models.validation import ProtectionLedger, ProtectionResult
from route_agent.parser.policy import (
    DEFAULT_CHEMISTRY,
    ChemistryPolicy,
    ProtectingGroupCensus,
)
from route_agent.parser.sites import resolve_site_token


def resolve_pending_handles(
    output: dict[str, Any], candidate: AgentCandidate
) -> dict[str, Any]:
    handle = handle_from_process(candidate.process)
    if handle is None:
        return output
    protected = dict(output.get("protected") or {})
    changed = False
    for token, group in protected.items():
        if group != "pending":
            continue
        if token == candidate.site or token in tokens_in_site(candidate.site):
            protected[token] = handle
            changed = True
    if not changed:
        return output
    updated = dict(output)
    updated["protected"] = protected
    return updated


def recompute_candidate_protection(
    *,
    residues: Sequence[Residue],
    sites: Sequence[ResolvedSite],
    request: DesignRequest,
    prior: Mapping[str, Any],
    candidate: AgentCandidate,
    chemistry: ChemistryPolicy | None = None,
) -> ProtectionResult:
    """Rebuild occupancy from residues, then replay history and this process."""
    policy = chemistry or DEFAULT_CHEMISTRY
    base = ProtectingGroupCensus(chemistry=policy).census_base(residues)
    protected = dict(base.ledger.protected)
    for item in prior.get("history") or []:
        if not isinstance(item, Mapping):
            continue
        apply_process_protection(
            protected,
            site=str(item.get("site") or ""),
            process=str(item.get("process") or ""),
            family=item.get("family"),
            chemistry=policy,
            sites=sites,
        )
    apply_process_protection(
        protected,
        site=candidate.site,
        process=candidate.process,
        family=candidate.family,
        chemistry=policy,
        sites=sites,
    )
    return ProtectionResult(
        ledger=ProtectionLedger(
            protected=protected,
            policy_version=policy.policy_version,
            provenance=(
                *base.ledger.provenance,
                Provenance(
                    kind="inference",
                    basis=(
                        f"Recomputed protecting groups for {request.request_id} "
                        "from the residue census, prior.history, and the "
                        f"candidate process {candidate.process}."
                    ),
                ),
            ),
        ),
        errors=base.errors,
    )


def apply_process_protection(
    protected: dict[str, str],
    *,
    site: str,
    process: str,
    family: object,
    chemistry: ChemistryPolicy | None = None,
    sites: Sequence[ResolvedSite] = (),
) -> dict[str, str]:
    if not site:
        return protected
    policy = chemistry or DEFAULT_CHEMISTRY
    handle = handle_from_process(process)
    tokens = atom_tokens_for_site(sites, site) or target_tokens(protected, site)
    if handle is not None:
        for token in tokens:
            protected[token] = handle
        return protected
    if _is_branching(family, policy):
        for token in tokens:
            protected[token] = "pending"
    return protected


def target_tokens(protected: Mapping[str, str], site: str) -> set[str]:
    parts = tokens_in_site(site)
    matched = {token for token in protected if token == site or token in parts}
    if matched:
        return matched
    return {site}


def atom_tokens_for_site(sites: Sequence[ResolvedSite], site: str) -> set[str]:
    tokens: set[str] = set()
    for resolved in sites:
        if resolve_site_token(resolved) != site and resolved.requested_token != site:
            continue
        tokens.update(
            atom.token
            for atom in resolved.atoms
            if atom.kind in {"position", "n_term", "c_term"}
        )
    return tokens


def tokens_in_site(site: str) -> set[str]:
    return {
        token for token in site.replace(",", " ").replace("-", " ").split() if token
    }


def handle_from_process(process_id: str) -> str | None:
    lowered = process_id.lower()
    if "ivdde" in lowered or "iv-dde" in lowered:
        return "ivDde"
    if "mtt" in lowered:
        return "Mtt"
    if "alloc" in lowered:
        return "Alloc"
    if "acm" in lowered:
        return "Acm"
    if "dde" in lowered:
        return "Dde"
    return None


def _is_branching(family: object, chemistry: ChemistryPolicy) -> bool:
    values = {item.value for item in chemistry.branching_families}
    if isinstance(family, str):
        return family in values
    return family in chemistry.branching_families
