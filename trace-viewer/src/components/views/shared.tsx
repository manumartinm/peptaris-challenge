import { useEffect, useState } from "react";
import { formatCount, formatTokens, formatUsd, humanize, shortRef } from "../../lib/format";
import type {
  AgentCandidate,
  AgentResult,
  CandidatePostGraphResult,
  CostBreakdown,
  PostGraphValidationReport,
  Provenance,
} from "../../types/trace";
import { BulletList, EmptyValue, PassChip, Section } from "../ui";

export function CostLine({ cost }: { cost?: CostBreakdown }) {
  if (!cost) return <EmptyValue />;
  return (
    <p className="muted">
      {formatCount(cost.calls, "call")} · {formatTokens(cost.input_tokens + cost.output_tokens)} tokens ·{" "}
      {formatUsd(cost.cost_usd)}
    </p>
  );
}

export function CandidateLabel({
  nodeId,
  candidate,
  selected,
  tied,
}: {
  nodeId: string;
  candidate: AgentCandidate | null;
  selected?: boolean;
  tied?: boolean;
}) {
  return (
    <div className="candidate-label">
      <strong>{nodeId}</strong>
      {candidate ? (
        <span>
          {candidate.process} · {humanize(candidate.family)} at {candidate.site}
        </span>
      ) : (
        <EmptyValue />
      )}
      {selected ? <span className="chip chip-navy">best</span> : null}
      {tied ? <span className="chip chip-warn">tied</span> : null}
    </div>
  );
}

function candidateOptionLabel(
  item: CandidatePostGraphResult,
  selectedId: string | null,
  tiedIds: string[],
): string {
  const parts = [item.node_id];
  if (item.candidate) {
    parts.push(
      `${item.candidate.process} · ${humanize(item.candidate.family)} at ${item.candidate.site}`,
    );
  }
  if (item.node_id === selectedId) parts.push("best");
  else if (tiedIds.includes(item.node_id)) parts.push("tied");
  return parts.join(" · ");
}

function sortedCandidates(
  candidates: CandidatePostGraphResult[],
  selectedId: string | null,
): CandidatePostGraphResult[] {
  return [...candidates].sort((left, right) => {
    if (left.node_id === selectedId) return -1;
    if (right.node_id === selectedId) return 1;
    return 0;
  });
}

export function useActiveCandidate(report: PostGraphValidationReport) {
  const fallbackId = report.selected_id ?? report.candidates[0]?.node_id ?? "";
  const [nodeId, setNodeId] = useState(fallbackId);

  useEffect(() => {
    setNodeId(fallbackId);
  }, [report.request_id, fallbackId]);

  const item =
    report.candidates.find((candidate) => candidate.node_id === nodeId) ??
    report.candidates[0] ??
    null;

  return { nodeId: item?.node_id ?? "", setNodeId, item };
}

export function CandidateNodeSelect({
  candidates,
  selectedId,
  tiedIds,
  value,
  onChange,
}: {
  candidates: CandidatePostGraphResult[];
  selectedId: string | null;
  tiedIds: string[];
  value: string;
  onChange: (nodeId: string) => void;
}) {
  if (candidates.length === 0) return null;
  return (
    <label className="node-select-label">
      Node
      <select
        className="node-select"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        {sortedCandidates(candidates, selectedId).map((item) => (
          <option key={item.node_id} value={item.node_id}>
            {candidateOptionLabel(item, selectedId, tiedIds)}
          </option>
        ))}
      </select>
    </label>
  );
}

export function CitationList({ citations }: { citations: Provenance[] }) {
  if (citations.length === 0) return <EmptyValue />;
  return (
    <ul className="stack-list">
      {citations.map((citation, index) => (
        <li key={`${citation.ref ?? citation.basis ?? index}`}>
          <strong>{humanize(citation.kind)}</strong>
          {citation.ref ? ` · ${shortRef(citation.ref)}` : ""}
          {citation.basis ? <p>{citation.basis}</p> : null}
          {citation.ref ? <p className="muted mono">{citation.ref}</p> : null}
        </li>
      ))}
    </ul>
  );
}

export function AgentResultPanel({
  title,
  result,
}: {
  title: string;
  result: AgentResult | null;
}) {
  if (!result) {
    return (
      <Section title={title}>
        <EmptyValue />
      </Section>
    );
  }

  return (
    <Section title={title}>
      <div className="stack">
        <div className="node-detail-title">
          <PassChip passed={result.passed} />
          {result.confidence ? (
            <span className="chip chip-neutral">{humanize(result.confidence)}</span>
          ) : null}
          {result.objective ? <span className="muted">{humanize(result.objective)}</span> : null}
        </div>
        {result.resolution ? <p>{result.resolution}</p> : null}
        <div>
          <h3 className="inline-heading">Findings</h3>
          {result.findings.length === 0 ? (
            <EmptyValue />
          ) : (
            <ul className="stack-list">
              {result.findings.map((finding) => (
                <li key={finding.description}>
                  <strong>{humanize(finding.kind)}</strong>
                  <p>{finding.description}</p>
                  {finding.affected.length > 0 ? (
                    <p className="muted">{finding.affected.join(", ")}</p>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <h3 className="inline-heading">Gaps</h3>
          <BulletList items={result.gaps} />
        </div>
        <div>
          <h3 className="inline-heading">Unknowns</h3>
          <BulletList items={result.unknowns} />
        </div>
        <div>
          <h3 className="inline-heading">Citations</h3>
          <CitationList citations={result.citations} />
        </div>
      </div>
    </Section>
  );
}
