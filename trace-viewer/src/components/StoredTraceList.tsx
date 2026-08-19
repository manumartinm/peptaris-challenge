import type { MouseEvent } from "react";
import { humanize } from "../lib/format";
import { jobHref, requestHref } from "../lib/routes";
import type { StoredTrace } from "../types/job";
import { VerdictChip } from "./ui";

interface StoredTraceListProps {
  traces: StoredTrace[];
  error: string | null;
  busyId: string | null;
  onOpen: (jobId: string) => void;
}

function formatWhen(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export function StoredTraceList({ traces, error, busyId, onOpen }: StoredTraceListProps) {
  if (error) {
    return (
      <section className="trace-shelf">
        <p className="dropzone-kicker">Job traces</p>
        <p className="dropzone-copy">
          The API is not listing <code>traces/jobs</code> yet. Start{" "}
          <code>uv run route-agent-api</code> from the interview root, or drop a file below.
        </p>
      </section>
    );
  }

  if (traces.length === 0) {
    return (
      <section className="trace-shelf">
        <p className="dropzone-kicker">Job traces</p>
        <p className="dropzone-copy">
          Completed runs land in <code>traces/jobs</code> and appear here.
        </p>
      </section>
    );
  }

  return (
    <section className="trace-shelf">
      <p className="dropzone-kicker">Job traces</p>
      <h2>Open a completed run</h2>
      <p className="dropzone-copy">
        These files are already on disk. New jobs show up here when they finish.
      </p>
      <ul className="trace-shelf-list">
        {traces.map((item) => (
          <li key={item.job_id}>
            <a
              className="trace-shelf-item"
              href={jobHref(item.job_id)}
              title={jobHref(item.job_id)}
              aria-disabled={busyId !== null}
              onClick={(event: MouseEvent<HTMLAnchorElement>) => {
                if (
                  busyId !== null ||
                  event.metaKey ||
                  event.ctrlKey ||
                  event.shiftKey ||
                  event.altKey ||
                  event.button !== 0
                ) {
                  if (busyId !== null) event.preventDefault();
                  return;
                }
                event.preventDefault();
                onOpen(item.job_id);
              }}
            >
              <span className="trace-shelf-main">
                <span className="trace-shelf-title">
                  {item.parent_name || item.request_id}
                </span>
                <span className="file-name">{item.file_name}</span>
                <span className="file-name">{requestHref(item.request_id)}</span>
              </span>
              <span className="trace-shelf-meta">
                {item.verdict ? <VerdictChip verdict={item.verdict} /> : null}
                {item.confidence ? (
                  <span className="trace-shelf-when">{humanize(item.confidence)}</span>
                ) : null}
                <span className="trace-shelf-when">{formatWhen(item.modified_at)}</span>
                {busyId === item.job_id ? <span className="trace-shelf-when">Opening…</span> : null}
              </span>
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}
