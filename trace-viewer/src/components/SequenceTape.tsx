import { modifiedSites } from "../lib/explain";
import type { PipelineTrace } from "../types/trace";

function siteIndex(token: string): number | null {
  const match = token.match(/^[A-Z](\d+)$/i);
  return match ? Number(match[1]) : null;
}

export function SequenceTape({ trace }: { trace: PipelineTrace }) {
  const sequence = trace.verdict.resolved_sequence || trace.request.sequence;
  if (!sequence) return null;
  const sites = modifiedSites(trace);
  const marked = new Set(
    [...sites]
      .map(siteIndex)
      .filter((index): index is number => index !== null),
  );

  return (
    <ol className="sequence-tape" aria-label="Resolved peptide sequence">
      {sequence.split("").map((letter, index) => {
        const position = index + 1;
        const markedResidue = marked.has(position);
        return (
          <li
            key={`${letter}${position}`}
            className={markedResidue ? "residue marked" : "residue"}
            title={`${letter}${position}`}
          >
            <span className="residue-index">{position}</span>
            <span className="residue-letter">{letter}</span>
          </li>
        );
      })}
    </ol>
  );
}
