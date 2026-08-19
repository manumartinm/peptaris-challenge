import { humanize } from "../../lib/format";
import type { PipelineTrace } from "../../types/trace";
import { BulletList, EmptyValue, Section, VerdictChip } from "../ui";
import { AgentResultPanel, CostLine } from "./shared";

export function JudgeView({ trace }: { trace: PipelineTrace }) {
  return (
    <div className="view-stack">
      <Section title="Assembled verdict">
        <div className="verdict-row">
          <VerdictChip verdict={trace.verdict.verdict} />
          <p className="headline">{humanize(trace.verdict.confidence)} confidence</p>
        </div>
        <CostLine cost={trace.cost.objectives.final_judge} />
      </Section>

      <AgentResultPanel title="Final judge" result={trace.judge} />

      <Section title="Verdict conflicts">
        {trace.verdict.conflicts.length === 0 ? (
          <EmptyValue />
        ) : (
          <ul className="stack-list">
            {trace.verdict.conflicts.map((conflict) => (
              <li key={`${conflict.kind}-${conflict.description}`}>
                <strong>{humanize(conflict.severity)}</strong> · {humanize(conflict.kind)}
                <p>{conflict.description}</p>
                {conflict.resolution ? <p className="muted">{conflict.resolution}</p> : null}
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Verdict unknowns">
        <BulletList items={trace.verdict.unknowns} />
      </Section>
    </div>
  );
}
