"""Typed pipeline events used by ``--explain`` and optional trace playback."""

from __future__ import annotations

from typing import Any, Literal

from route_agent.models.frozen import FrozenModel

StageName = Literal[
    "loading",
    "validating",
    "walking",
    "post_graph",
    "judging",
    "assembling",
    "writing",
]
NodeStatus = Literal["pass", "fail", "degraded"]
EventKind = Literal[
    "stage_started",
    "stage_finished",
    "validation_stage",
    "node_created",
    "candidate_evaluated",
    "branch_pruned",
    "frontier_changed",
    "molecular_validated",
    "intent_checked",
    "winner_selected",
    "judge_finished",
    "verdict_ready",
]


class StateDiff(FrozenModel):
    """Bounded semantic changes from a parent node. Never includes secrets."""

    protecting_groups: dict[str, str] = {}
    termini: dict[str, str] = {}
    connectivity_added: tuple[dict[str, str], ...] = ()
    fragments: tuple[str, ...] = ()
    overrides: dict[str, str] = {}
    unknowns: tuple[str, ...] = ()
    route_step: dict[str, Any] | None = None


class PipelineEvent(FrozenModel):
    kind: EventKind
    stage: StageName
    request_id: str | None = None
    node_id: str | None = None
    parent_id: str | None = None
    family: str | None = None
    process: str | None = None
    site: str | None = None
    status: NodeStatus | None = None
    reason: str | None = None
    kept: bool | None = None
    frontier: tuple[str, ...] = ()
    calls: int | None = None
    cost_usd: float | None = None
    duration_ms: float | None = None
    current: int | None = None
    total: int | None = None
    diff: StateDiff | None = None
    message: str | None = None


def diff_state(
    parent: dict[str, Any] | None,
    child: dict[str, Any] | None,
    *,
    route_step: dict[str, Any] | None = None,
) -> StateDiff:
    """Compare ledger-like dicts and keep only the public chemistry fields."""
    before = parent or {}
    after = child or {}
    protecting = _changed_mapping(
        before.get("protected") or {}, after.get("protected") or {}
    )
    termini = _changed_mapping(before.get("termini") or {}, after.get("termini") or {})
    parent_bonds = _bond_keys(before.get("permanent_connectivity") or ())
    added = tuple(
        item
        for item in after.get("permanent_connectivity") or ()
        if isinstance(item, dict) and _bond_key(item) not in parent_bonds
    )
    parent_fragments = {
        _fragment_label(item) for item in before.get("product_fragments") or ()
    }
    fragments = tuple(
        _fragment_label(item)
        for item in after.get("product_fragments") or ()
        if _fragment_label(item) not in parent_fragments
    )
    overrides = _changed_mapping(
        before.get("residue_overrides") or {}, after.get("residue_overrides") or {}
    )
    parent_unknowns = set(before.get("product_unknowns") or ())
    unknowns = tuple(
        item
        for item in after.get("product_unknowns") or ()
        if item not in parent_unknowns
    )
    return StateDiff(
        protecting_groups={key: str(value) for key, value in protecting.items()},
        termini={key: str(value) for key, value in termini.items()},
        connectivity_added=tuple(
            {str(key): str(value) for key, value in item.items()} for item in added
        ),
        fragments=fragments,
        overrides={key: str(value) for key, value in overrides.items()},
        unknowns=tuple(str(item) for item in unknowns),
        route_step=route_step,
    )


def _changed_mapping(before: object, after: object) -> dict[str, Any]:
    old = before if isinstance(before, dict) else {}
    new = after if isinstance(after, dict) else {}
    changed: dict[str, Any] = {}
    for key, value in new.items():
        if old.get(key) != value:
            changed[str(key)] = value
    return changed


def _bond_keys(items: object) -> set[tuple[str, ...]]:
    keys: set[tuple[str, ...]] = set()
    if not isinstance(items, list | tuple):
        return keys
    for item in items:
        if isinstance(item, dict):
            keys.add(_bond_key(item))
    return keys


def _bond_key(item: dict[str, Any]) -> tuple[str, ...]:
    return tuple(f"{key}={item[key]}" for key in sorted(item) if item[key] is not None)


def _fragment_label(item: object) -> str:
    if not isinstance(item, dict):
        return str(item)
    catalog = item.get("catalog_id") or item.get("instance_id") or "fragment"
    site = item.get("site")
    if site:
        return f"{catalog}@{site}"
    return str(catalog)
