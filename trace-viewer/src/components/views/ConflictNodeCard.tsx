import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { handleForSite } from "../../lib/explain";
import type { TreeNodeData } from "../../lib/graph";
import { StatusChip } from "../ui";

export function ConflictNodeCard({ data }: NodeProps<Node<TreeNodeData>>) {
  const { node, selectedId, survivingIds } = data;
  const selected = node.id === selectedId;
  const surviving = survivingIds.includes(node.id);
  const handle = handleForSite(node.state.output, node.candidate?.site);
  const label = node.candidate
    ? `${node.candidate.process} · ${node.candidate.site}${handle ? ` · ${handle}` : ""}`
    : node.state.node_type;

  return (
    <div className={`flow-node status-${node.state.status}${selected ? " is-selected" : ""}`}>
      <Handle type="target" position={Position.Top} />
      <div className="flow-node-top">
        <StatusChip status={node.state.status} />
        {selected ? <span className="chip chip-navy">selected</span> : null}
        {surviving && !selected ? <span className="chip chip-neutral">surviving</span> : null}
      </div>
      <strong>{node.id}</strong>
      <p>{label}</p>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}
