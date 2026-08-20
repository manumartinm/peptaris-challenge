import { formatTokens, formatUsd, humanize } from "../../lib/format";
import {
  candidateProtectionEvents,
  changedProtectingGroups,
  handleForSite,
} from "../../lib/explain";
import type {
  ConflictNodeReport,
  JsonObject,
  PipelineEvent,
  StateLedger,
} from "../../types/trace";
import { EmptyValue, StatusChip } from "../ui";

function MapBlock({ title, value }: { title: string; value?: Record<string, string> }) {
  const entries = Object.entries(value ?? {});
  return (
    <div>
      <h4>{title}</h4>
      {entries.length === 0 ? (
        <EmptyValue />
      ) : (
        <ul className="kv-list">
          {entries.map(([key, item]) => (
            <li key={key}>
              <code>{key}</code>
              <span>{item}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function JsonLines({ value }: { value: unknown }) {
  if (value == null) return <EmptyValue />;
  if (Array.isArray(value) && value.length === 0) return <EmptyValue />;
  return <pre className="mini-json">{JSON.stringify(value, null, 2)}</pre>;
}

export function NodeDetail({
  node,
  selectedId,
  parent,
  events,
}: {
  node: ConflictNodeReport | null;
  selectedId: string | null;
  parent?: ConflictNodeReport | null;
  events?: PipelineEvent[];
}) {
  if (!node) {
    return (
      <aside className="node-detail">
        <p className="muted">Select a node to inspect its candidate, ledger, and LLM calls.</p>
      </aside>
    );
  }

  const ledger: StateLedger = node.state.output;
  const history = ledger.history ?? [];
  const chosen = selectedId === node.id;
  const changed = changedProtectingGroups(parent?.state.output, ledger);
  const prepared = candidateProtectionEvents(events ?? [], node);
  const siteHandle = handleForSite(ledger, node.candidate?.site);

  return (
    <aside className="node-detail">
      <header>
        <div className="node-detail-title">
          <h3>{node.id}</h3>
          <StatusChip status={node.state.status} />
          {chosen ? <span className="chip chip-navy">selected</span> : null}
        </div>
        <p className="muted">{humanize(node.state.node_type)}</p>
      </header>

      <section>
        <h4>Candidate</h4>
        {node.candidate ? (
          <p>
            {node.candidate.process} · {humanize(node.candidate.family)} at {node.candidate.site}
            {siteHandle ? ` · ${siteHandle}` : ""}
          </p>
        ) : (
          <EmptyValue />
        )}
      </section>

      <section>
        <h4>Agent result</h4>
        {node.agent_result ? (
          <div className="stack">
            <p>
              {node.agent_result.passed === null
                ? "No disponible"
                : node.agent_result.passed
                  ? "Passed"
                  : "Did not pass"}
              {node.agent_result.confidence ? ` · ${humanize(node.agent_result.confidence)}` : ""}
            </p>
            {node.agent_result.resolution ? <p>{node.agent_result.resolution}</p> : null}
            {node.agent_result.findings.map((finding) => (
              <p key={finding.description}>
                <strong>{humanize(finding.kind)}:</strong> {finding.description}
              </p>
            ))}
          </div>
        ) : (
          <EmptyValue />
        )}
      </section>

      <section>
        <h4>Prior operations</h4>
        {history.length === 0 ? (
          <EmptyValue />
        ) : (
          <ul className="stack-list">
            {history.map((item) => (
              <li key={`${item.process}-${item.site}`}>
                {item.process} at {item.site}
                {item.passed === null ? "" : item.passed ? " · passed" : " · failed"}
              </li>
            ))}
          </ul>
        )}
        {prepared.map((event, index) => (
          <p key={`${event.process}-${index}`} className="muted">
            {event.message || "Protecting groups recomputed from census, prior work, and this process."}
          </p>
        ))}
      </section>

      <MapBlock title="Protecting groups changed" value={changed} />
      <MapBlock title="Protecting groups" value={ledger.protected} />
      <MapBlock title="Termini" value={ledger.termini} />
      <MapBlock title="Catalysts used" value={ledger.catalysts_used} />

      <section>
        <h4>Connectivity</h4>
        <JsonLines value={ledger.permanent_connectivity} />
      </section>

      <section>
        <h4>Route step</h4>
        <JsonLines value={node.state.route_step as JsonObject | null} />
      </section>

      <section>
        <h4>LLM calls</h4>
        {node.state.llm_calls.length === 0 ? (
          <EmptyValue />
        ) : (
          <ul className="stack-list">
            {node.state.llm_calls.map((call) => (
              <li key={call.call_id}>
                {call.objective} · {call.model}
                <br />
                {formatTokens(call.input_tokens + call.output_tokens)} tokens · {formatUsd(call.cost_usd)}
              </li>
            ))}
          </ul>
        )}
      </section>
    </aside>
  );
}
