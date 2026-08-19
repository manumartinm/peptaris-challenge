import { useState } from "react";
import { useStoredTraces } from "../hooks/useStoredTraces";
import type { DesignRequestDraft } from "../lib/validateDesignRequest";
import { validateDesignRequest } from "../lib/validateDesignRequest";
import type { JobState } from "../types/job";
import { DesignRequestForm } from "./DesignRequestForm";
import { JobProgress } from "./JobProgress";
import { StoredTraceList } from "./StoredTraceList";
import { UploadDropzone } from "./UploadDropzone";

type LaunchMode = "choose" | "form" | "open";

interface LaunchViewProps {
  draft: DesignRequestDraft;
  job: JobState | null;
  submitting: boolean;
  busyFile: boolean;
  formError: string | null;
  onDraftChange: (draft: DesignRequestDraft) => void;
  onSubmit: () => void;
  onFile: (file: File) => void;
  onOpenStored: (jobId: string) => void;
  openingJobId: string | null;
  onRetry: () => void;
}

export function LaunchView({
  draft,
  job,
  submitting,
  busyFile,
  formError,
  onDraftChange,
  onSubmit,
  onFile,
  onOpenStored,
  openingJobId,
  onRetry,
}: LaunchViewProps) {
  const [mode, setMode] = useState<LaunchMode>("choose");
  const [clientErrors, setClientErrors] = useState<string[]>([]);
  const browsing = !job || job.status === "failed";
  const stored = useStoredTraces(browsing);

  function submit() {
    const errors = validateDesignRequest(draft);
    setClientErrors(errors);
    if (errors.length === 0) onSubmit();
  }

  if (job && job.status !== "failed") {
    return <JobProgress job={job} />;
  }

  if (mode === "open") {
    return (
      <div className="launch-stack">
        <StoredTraceList
          traces={stored.traces}
          error={stored.error}
          busyId={openingJobId}
          onOpen={onOpenStored}
        />
        <UploadDropzone onFile={onFile} busy={busyFile} />
        <button type="button" className="ghost-button dark" onClick={() => setMode("choose")}>
          Back
        </button>
      </div>
    );
  }

  if (mode === "form" || job?.status === "failed") {
    return (
      <section className="launch-card">
        <p className="dropzone-kicker">New request</p>
        <h2>Submit a design</h2>
        <p className="dropzone-copy">
          The pipeline runs locally. Progress appears here; the trace opens when it finishes.
        </p>
        {formError ? <p className="form-errors">{formError}</p> : null}
        <DesignRequestForm
          draft={draft}
          errors={clientErrors}
          submitting={submitting}
          onChange={onDraftChange}
          onSubmit={submit}
        />
        <button
          type="button"
          className="ghost-button dark"
          onClick={() => {
            setMode("choose");
            onRetry();
          }}
        >
          Back
        </button>
      </section>
    );
  }

  return (
    <section className="launch-card">
      <p className="dropzone-kicker">Trace Explorer</p>
      <h2>Analyze a peptide design</h2>
      <p className="dropzone-copy">
        Submit a request to the local pipeline, or open a trace from today&apos;s runs.
      </p>
      <div className="launch-actions">
        <button type="button" className="primary-button" onClick={() => setMode("form")}>
          New request
        </button>
        <button type="button" className="ghost-button dark" onClick={() => setMode("open")}>
          Open existing trace
        </button>
      </div>
      <StoredTraceList
        traces={stored.traces}
        error={stored.error}
        busyId={openingJobId}
        onOpen={onOpenStored}
      />
    </section>
  );
}
