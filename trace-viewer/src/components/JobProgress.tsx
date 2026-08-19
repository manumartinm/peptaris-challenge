import { humanize } from "../lib/format";
import { JOB_PHASES, type JobState } from "../types/job";

export function JobProgress({ job }: { job: JobState }) {
  return (
    <section className="job-progress">
      <p className="dropzone-kicker">{job.status}</p>
      <h2>{job.request_id}</h2>
      <p className="muted">{job.activity || "Waiting for the first pipeline event."}</p>
      {job.progress?.current != null && job.progress.total != null ? (
        <p className="muted">
          {job.progress.current} / {job.progress.total}
          {job.progress.label ? ` · ${job.progress.label}` : ""}
        </p>
      ) : null}
      <ol className="phase-stepper">
        {JOB_PHASES.map((phase) => {
          const done = job.completed_phases.includes(phase);
          const active = job.phase === phase && job.status === "running";
          return (
            <li key={phase} className={done ? "done" : active ? "active" : ""}>
              <span>{humanize(phase)}</span>
            </li>
          );
        })}
      </ol>
      {job.error ? <p className="form-errors">{job.error}</p> : null}
    </section>
  );
}
