import type { PipelineTrace } from "../../types/trace";
import { EmptyValue, MetaGrid, Section } from "../ui";
import { AgentResultPanel, CandidateLabel } from "./shared";

export function IntentView({ trace }: { trace: PipelineTrace }) {
  const report = trace.post_graph;
  return (
    <div className="view-stack">
      <Section title="Intent check">
        <p className="intent">{trace.request.intent || <EmptyValue />}</p>
        <MetaGrid
          items={[
            { label: "Selected", value: report.selected_id },
            { label: "Tied", value: report.tied_ids.join(", ") || null },
          ]}
        />
      </Section>
      {report.candidates.length === 0 ? (
        <EmptyValue />
      ) : (
        report.candidates.map((item) => (
          <article key={item.node_id} className="candidate-card">
            <CandidateLabel
              nodeId={item.node_id}
              candidate={item.candidate}
              selected={item.node_id === report.selected_id}
              tied={report.tied_ids.includes(item.node_id)}
            />
            <AgentResultPanel title="check_intent" result={item.intent} />
          </article>
        ))
      )}
    </div>
  );
}
