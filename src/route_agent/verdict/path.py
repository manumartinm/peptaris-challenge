from __future__ import annotations

from route_agent.models.conflict import ConflictNode, ConflictTree


def collect_winning_path(
    tree: ConflictTree, selected_id: str | None
) -> tuple[str, ...]:
    node_id = selected_id or tree.root_id
    if node_id not in tree.graph:
        return (tree.root_id,)
    path = [node_id]
    node = tree.node(node_id)
    while node.state.parents:
        parent_id = node.state.parents[0]
        path.append(parent_id)
        node = tree.node(parent_id)
    path.reverse()
    return tuple(path)


def path_nodes(tree: ConflictTree, selected_id: str | None) -> tuple[ConflictNode, ...]:
    return tuple(
        tree.node(node_id) for node_id in collect_winning_path(tree, selected_id)
    )
