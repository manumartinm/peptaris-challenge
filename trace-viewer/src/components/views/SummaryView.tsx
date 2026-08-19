import { explainTrace } from "../../lib/explain";
import { formatCount, formatTokens, formatUsd, humanize } from "../../lib/format";
import type { TabId } from "../../types/tabs";
import type { PipelineTrace } from "../../types/trace";
import { SequenceTape } from "../SequenceTape";
import { BulletList, EmptyValue, MetaGrid, PassChip, Section, StatusChip, VerdictChip } from "../ui";

function selectedCandidate(trace: PipelineTrace) {
  return (
    trace.post_graph.candidates.find((item) => item.node_id === trace.post_graph.selected_id) ??
    null
  );
}

export function SummaryView({
  trace,
  onOpen,
}: {
  trace: PipelineTrace;
  onOpen: (tab: TabId) => void;
}) {
  const why = explainTrace(trace);
  const selected = selectedCandidate(trace);
  const candidate = selected?.candidate;

  return (
    <div className="view-stack">
      <Section title="What happened">
        <div className="verdict-row">
          <VerdictChip verdict={trace.verdict.verdict} />
          <p className="headline">{why.headline}.</p>
        </div>
        <SequenceTape trace={trace} />
        <MetaGrid
          items={[
            { label: "Request", value: trace.request_id },
            { label: "Parent", value: trace.request.parent_name },
            { label: "Confidence", value: humanize(trace.verdict.confidence) },
            {
              label: "Selected candidate",
              value: candidate
                ? `${candidate.process} at ${candidate.site}`
                : trace.post_graph.selected_id,
            },
            { label: "LLM calls", value: formatCount(trace.cost.total.calls, "call") },
            { label: "Tokens", value: formatTokens(trace.cost.total.input_tokens + trace.cost.total.output_tokens) },
            { label: "Cost", value: formatUsd(trace.cost.total.cost_usd) },
            { label: "C-terminus", value: humanize(trace.request.parent_c_terminus) },
          ]}
        />
      </Section>

      <nav className="step-strip" aria-label="Pipeline steps">
        <button type="button" className="step-card" onClick={() => onOpen("validate")}>
          <span className="route-stage">Validate</span>
          <StatusChip status={trace.validation.state.status} />
        </button>
        <button type="button" className="step-card" onClick={() => onOpen("walk")}>
          <span className="route-stage">Walk</span>
          <span>{formatCount(trace.tree.surviving_ids.length, "survivor")}</span>
        </button>
        <button type="button" className="step-card" onClick={() => onOpen("molecular")}>
          <span className="route-stage">Molecular</span>
          <PassChip passed={selected?.molecular?.two_d?.valid ?? null} />
        </button>
        <button type="button" className="step-card" onClick={() => onOpen("intent")}>
          <span className="route-stage">Intent</span>
          <PassChip passed={selected?.intent?.passed ?? null} />
        </button>
        <button type="button" className="step-card" onClick={() => onOpen("judge")}>
          <span className="route-stage">Judge</span>
          <PassChip passed={trace.judge?.passed ?? null} />
        </button>
      </nav>

      <Section title="Design request">
        <p className="intent">{trace.request.intent || <EmptyValue />}</p>
        <ul className="stack-list">
          {trace.request.modifications.map((modification) => (
            <li key={`${modification.family}-${modification.site}`}>
              <strong>{humanize(modification.family)}</strong> at {modification.site}
              {modification.detail ? ` — ${modification.detail}` : ""}
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Why">
        <BulletList items={why.bullets} />
      </Section>

      <Section title="Synthetic route">
        {trace.verdict.route.length === 0 ? (
          <EmptyValue />
        ) : (
          <ol className="route-list">
            {trace.verdict.route.map((step) => (
              <li key={step.step}>
                <span className="route-index">{String(step.step).padStart(2, "0")}</span>
                <div>
                  <p className="route-stage">{humanize(step.stage)}</p>
                  <p>{step.operation}</p>
                </div>
              </li>
            ))}
          </ol>
        )}
      </Section>

      <div className="split-grid">
        <Section title="Conflicts">
          {trace.verdict.conflicts.length === 0 ? (
            <EmptyValue />
          ) : (
            <ul className="stack-list">
              {trace.verdict.conflicts.map((conflict) => (
                <li key={`${conflict.kind}-${conflict.description}`}>
                  <strong>{humanize(conflict.severity)}</strong> · {humanize(conflict.kind)}
                  <p>{conflict.description}</p>
                </li>
              ))}
            </ul>
          )}
        </Section>
        <Section title="Unknowns">
          <BulletList items={trace.verdict.unknowns} />
        </Section>
      </div>
    </div>
  );
}
