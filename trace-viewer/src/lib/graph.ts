import type { Edge, Node } from "@xyflow/react";
import type { ConflictNodeReport } from "../types/trace";

export interface TreeNodeData extends Record<string, unknown> {
  node: ConflictNodeReport;
  selectedId: string | null;
  survivingIds: string[];
}

export type TreeFlowNode = Node<TreeNodeData, "conflict">;

const NODE_WIDTH = 264;
const GAP_X = 36;
const GAP_Y = 118;

export function buildFlowGraph(
  nodes: ConflictNodeReport[],
  selectedId: string | null,
  survivingIds: string[],
): { nodes: TreeFlowNode[]; edges: Edge[] } {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const childIds = new Set(nodes.flatMap((node) => node.children));
  const roots = nodes.filter((node) => !childIds.has(node.id));
  const depth = new Map<string, number>();
  const queue = roots.map((node) => node.id);
  for (const root of roots) depth.set(root.id, 0);

  while (queue.length > 0) {
    const id = queue.shift();
    if (!id) break;
    const current = byId.get(id);
    if (!current) continue;
    for (const child of current.children) {
      if (!depth.has(child)) {
        depth.set(child, (depth.get(id) ?? 0) + 1);
        queue.push(child);
      }
    }
  }

  const levels = new Map<number, string[]>();
  for (const node of nodes) {
    const level = depth.get(node.id) ?? 0;
    const bucket = levels.get(level) ?? [];
    bucket.push(node.id);
    levels.set(level, bucket);
  }

  const flowNodes: TreeFlowNode[] = [];
  const edges: Edge[] = [];

  for (const [level, ids] of levels) {
    const totalWidth = ids.length * NODE_WIDTH + Math.max(0, ids.length - 1) * GAP_X;
    const startX = -totalWidth / 2;
    ids.forEach((id, index) => {
      const node = byId.get(id);
      if (!node) return;
      flowNodes.push({
        id,
        type: "conflict",
        position: {
          x: startX + index * (NODE_WIDTH + GAP_X),
          y: level * GAP_Y,
        },
        data: { node, selectedId, survivingIds },
      });
      for (const child of node.children) {
        edges.push({
          id: `${id}->${child}`,
          source: id,
          target: child,
        });
      }
    });
  }

  return { nodes: flowNodes, edges };
}
