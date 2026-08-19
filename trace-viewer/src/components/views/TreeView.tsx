import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  type NodeMouseHandler,
} from "@xyflow/react";
import { useMemo, useState } from "react";
import { buildFlowGraph, type TreeFlowNode } from "../../lib/graph";
import type { PipelineTrace } from "../../types/trace";
import { NodeDetail } from "./NodeDetail";
import { ConflictNodeCard } from "./ConflictNodeCard";
import "@xyflow/react/dist/style.css";

const nodeTypes = { conflict: ConflictNodeCard };

export function TreeView({ trace }: { trace: PipelineTrace }) {
  const selectedId = trace.post_graph.selected_id;
  const { nodes, edges } = useMemo(
    () => buildFlowGraph(trace.tree.nodes, selectedId, trace.tree.surviving_ids),
    [trace, selectedId],
  );
  const [activeId, setActiveId] = useState<string | null>(selectedId);
  const active = trace.tree.nodes.find((node) => node.id === activeId) ?? null;

  const onNodeClick: NodeMouseHandler = (_event, node) => {
    setActiveId(node.id);
  };

  return (
    <div className="tree-layout">
      <div className="tree-canvas">
        <ReactFlow<TreeFlowNode>
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodeClick={onNodeClick}
          fitView
          minZoom={0.3}
          proOptions={{ hideAttribution: true }}
        >
          <Background gap={18} color="#c5ceda" />
          <Controls />
          <MiniMap pannable zoomable />
        </ReactFlow>
      </div>
      <NodeDetail node={active} selectedId={selectedId} />
    </div>
  );
}
