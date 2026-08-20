import type { PipelineTrace } from "../../types/trace";
import { EmptyValue, MetaGrid, Section } from "../ui";
import { AgentResultPanel, CandidateLabel, CandidateNodeSelect, useActiveCandidate } from "./shared";

export function IntentView({ trace }: { trace: PipelineTrace }) {
  const report = trace.post_graph;
  const { nodeId, setNodeId, item } = useActiveCandidate(report);

  return (
    <div className="view-stack">
      <Section
        title="Intent check"
        action={
          <CandidateNodeSelect
            candidates={report.candidates}
            selectedId={report.selected_id}
            tiedIds={report.tied_ids}
            value={nodeId}
            onChange={setNodeId}
          />
        }
      >
        <p className="intent">{trace.request.intent || <EmptyValue />}</p>
        <MetaGrid
          items={[
            { label: "Best", value: report.selected_id },
            { label: "Tied", value: report.tied_ids.join(", ") || null },
          ]}
        />
      </Section>
      {item ? (
        <article className="candidate-card">
          <CandidateLabel
            nodeId={item.node_id}
            candidate={item.candidate}
            selected={item.node_id === report.selected_id}
            tied={report.tied_ids.includes(item.node_id)}
          />
          <AgentResultPanel title="check_intent" result={item.intent} />
        </article>
      ) : (
        <EmptyValue />
      )}
    </div>
  );
}
