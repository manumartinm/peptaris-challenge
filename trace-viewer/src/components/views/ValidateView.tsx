import { formatCount, humanize } from "../../lib/format";
import type { PipelineTrace } from "../../types/trace";
import { BulletList, EmptyValue, MetaGrid, Section, StatusChip } from "../ui";
import { CitationList, CostLine } from "./shared";

export function ValidateView({ trace }: { trace: PipelineTrace }) {
  const validation = trace.validation;
  const ledger = validation.state.output;

  return (
    <div className="view-stack">
      <Section title="Validation">
        <div className="node-detail-title">
          <StatusChip status={validation.state.status} />
          <span className="muted">{validation.state.id}</span>
        </div>
        <CostLine cost={trace.cost.phases.validate} />
        <MetaGrid
          items={[
            { label: "Resolved sequence", value: validation.resolved_sequence },
            { label: "C-terminus", value: humanize(validation.parent_c_terminus) },
            { label: "Intent", value: validation.intent },
            { label: "Sites resolved", value: formatCount(validation.sites_resolved.length, "site") },
            { label: "Conflicts", value: formatCount(validation.conflicts.length, "conflict") },
            {
              label: "Route step",
              value: validation.state.route_step
                ? String(validation.state.route_step.operation ?? validation.state.route_step.stage ?? "")
                : null,
            },
          ]}
        />
      </Section>

      <Section title="Site map">
        {validation.site_map.length === 0 ? (
          <EmptyValue />
        ) : (
          <ul className="kv-list">
            {validation.site_map.map((entry) => (
              <li key={`${entry.requested}-${entry.resolved}`}>
                <code>{entry.requested}</code>
                <span>
                  {entry.resolved}
                  {entry.residue ? ` · ${entry.residue}` : ""}
                  {entry.note ? ` · ${entry.note}` : ""}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <div className="split-grid">
        <Section title="Protecting groups">
          {ledger.protected && Object.keys(ledger.protected).length > 0 ? (
            <ul className="kv-list">
              {Object.entries(ledger.protected).map(([site, group]) => (
                <li key={site}>
                  <code>{site}</code>
                  <span>{group}</span>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyValue />
          )}
        </Section>
        <Section title="Termini">
          {ledger.termini && Object.keys(ledger.termini).length > 0 ? (
            <ul className="kv-list">
              {Object.entries(ledger.termini).map(([end, kind]) => (
                <li key={end}>
                  <code>{end}</code>
                  <span>{humanize(kind)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyValue />
          )}
        </Section>
      </div>

      <Section title="Conflicts">
        {validation.conflicts.length === 0 ? (
          <EmptyValue />
        ) : (
          <ul className="stack-list">
            {validation.conflicts.map((conflict, index) => (
              <li key={index}>
                <pre className="mini-json">{JSON.stringify(conflict, null, 2)}</pre>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <div className="split-grid">
        <Section title="Unknowns">
          <BulletList items={validation.unknowns} />
        </Section>
        <Section title="Provenance">
          <CitationList citations={validation.state.provenance} />
        </Section>
      </div>
    </div>
  );
}
