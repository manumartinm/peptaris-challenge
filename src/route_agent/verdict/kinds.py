from __future__ import annotations

from route_agent.models.conflict import ConflictTree, ValidationResult
from route_agent.models.corpus import FamilyBinding
from route_agent.models.molecular import PostGraphValidationReport
from route_agent.models.verdict import SchemaConflictKind
from route_agent.verdict.path import collect_winning_path

SCHEMA_KINDS = {
    "protecting_group_orthogonality",
    "order_of_operations",
    "mutually_exclusive",
    "site_invalid",
    "reagent_incompatibility",
    "building_block_availability",
    "intent_not_achieved",
}
ON_RESIN_FAMILIES = {
    "lipidation",
    "pegylation",
    "glycosylation",
    "cyclization",
    "hydrocarbon_stapling",
    "biaryl_bisalkylation",
    "charge_hybrids",
}
UNMAPPED_PREFIX = "unmapped_permanent_family:"
CATALYST_KINDS = frozenset({"order_of_operations", "reagent_incompatibility"})
PD_MARKERS = ("pd", "palladium")
RU_MARKERS = ("ru", "ruthenium", "grubbs")


def schema_kind(kind: str) -> SchemaConflictKind | None:
    if kind in SCHEMA_KINDS:
        return kind  # type: ignore[return-value]
    return None


def parser_emitted_site_invalid(validation: ValidationResult) -> bool:
    return any(item.kind == "site_invalid" for item in validation.conflicts)


def has_head_to_tail_amide_clash(validation: ValidationResult) -> bool:
    cyclization = [
        binding
        for binding in validation.family_bindings
        if binding.family.value == "cyclization"
    ]
    amidation = [
        binding
        for binding in validation.family_bindings
        if binding.family.value == "c_term_amidation"
    ]
    if not cyclization or not amidation:
        return False
    return any(_is_head_to_tail(binding) for binding in cyclization)


def cli_kind_from_agent(
    kind: str, validation: ValidationResult
) -> SchemaConflictKind | None:
    mapped = schema_kind(kind)
    if mapped is None:
        return None
    if mapped != "site_invalid":
        return mapped
    if parser_emitted_site_invalid(validation):
        return "site_invalid"
    if has_head_to_tail_amide_clash(validation):
        return "mutually_exclusive"
    return "reagent_incompatibility"


def collect_unmapped_markers(
    tree: ConflictTree,
    selected_id: str | None,
    post_graph: PostGraphValidationReport,
) -> tuple[str, ...]:
    found: list[str] = []
    found.extend(_unmapped_items(post_graph.unknowns))
    node_ids: tuple[str, ...]
    if selected_id is not None:
        node_ids = collect_winning_path(tree, selected_id)
    else:
        node_ids = post_graph.surviving_ids or tree.surviving_ids
    for node_id in node_ids:
        if node_id not in tree.graph:
            continue
        output = tree.node(node_id).state.output or {}
        found.extend(_unmapped_items(output.get("product_unknowns") or ()))
    for candidate in post_graph.candidates:
        if selected_id is not None and candidate.node_id != selected_id:
            continue
        found.extend(_unmapped_items(candidate.molecular.unknowns))
        recipe = candidate.molecular.recipe
        if recipe is not None:
            found.extend(_unmapped_items(recipe.unknowns))
    return tuple(dict.fromkeys(found))


def unmapped_families(markers: tuple[str, ...]) -> frozenset[str]:
    families: set[str] = set()
    for item in markers:
        parts = item.split(":")
        if len(parts) >= 2:
            families.add(parts[1])
    return frozenset(families)


def path_has_kinds(tree: ConflictTree, selected_id: str, kinds: frozenset[str]) -> bool:
    for node_id in collect_winning_path(tree, selected_id):
        result = tree.node(node_id).agent_result
        if result is None:
            continue
        if any(schema_kind(item.kind) in kinds for item in result.findings):
            return True
    return False


def path_catalyst_conflict_kind(
    tree: ConflictTree, selected_id: str
) -> SchemaConflictKind | None:
    pd_nodes: list[str] = []
    ru_nodes: list[str] = []
    for node_id in collect_winning_path(tree, selected_id):
        classes = _catalyst_classes(tree, node_id)
        if "pd" in classes:
            pd_nodes.append(node_id)
        if "ru" in classes:
            ru_nodes.append(node_id)
    if not pd_nodes or not ru_nodes:
        return None
    if set(pd_nodes) & set(ru_nodes):
        return "reagent_incompatibility"
    return "order_of_operations"


def _catalyst_classes(tree: ConflictTree, node_id: str) -> set[str]:
    node = tree.node(node_id)
    used = (node.state.output or {}).get("catalysts_used") or {}
    parts = [str(key) for key in used]
    parts.extend(str(value) for value in used.values())
    if node.candidate is not None:
        parts.extend((node.candidate.family, node.candidate.process))
    blob = " ".join(parts).lower()
    classes: set[str] = set()
    if any(marker in blob for marker in PD_MARKERS) or "alloc" in blob:
        classes.add("pd")
    if any(marker in blob for marker in RU_MARKERS) or "hydrocarbon_stapling" in blob:
        classes.add("ru")
    return classes


def _unmapped_items(values: object) -> list[str]:
    found: list[str] = []
    if not isinstance(values, (list, tuple)):
        return found
    for item in values:
        text = str(item)
        if text.startswith(UNMAPPED_PREFIX):
            found.append(text)
    return found


def _is_head_to_tail(binding: FamilyBinding) -> bool:
    site = (binding.site or "").lower()
    processes = " ".join(binding.process_ids).lower().replace("-", "_")
    return "both termini" in site or "head_to_tail" in processes
