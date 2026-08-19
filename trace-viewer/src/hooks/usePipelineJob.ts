import { useEffect, useEffectEvent, useRef, useState } from "react";
import { ApiError, fetchJob, fetchJobTrace, submitJob } from "../lib/api";
import { toPayload, type DesignRequestDraft } from "../lib/validateDesignRequest";
import type { JobState } from "../types/job";

const POLL_MS = 5000;

export function usePipelineJob(
  onTrace: (raw: unknown, requestId: string, jobId: string) => void,
) {
  const [job, setJob] = useState<JobState | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const openedRef = useRef(false);
  const jobIdRef = useRef<string | null>(null);
  const onJobTrace = useEffectEvent(onTrace);

  useEffect(() => {
    if (!jobId) return undefined;
    let cancelled = false;
    let timer: number | undefined;

    const stop = () => {
      if (timer !== undefined) {
        window.clearInterval(timer);
        timer = undefined;
      }
    };

    const tick = async () => {
      try {
        const next = await fetchJob(jobId);
        if (cancelled) return;
        setJob(next);
        if (next.status === "completed" || next.status === "failed") {
          stop();
        }
        if (next.status === "completed" && !openedRef.current) {
          openedRef.current = true;
          const raw = await fetchJobTrace(jobId);
          if (cancelled) return;
          onJobTrace(raw, next.request_id, jobId);
        }
        if (next.status === "failed") {
          setError(next.error || "The job failed.");
        }
      } catch (exc) {
        if (cancelled) return;
        setError(exc instanceof Error ? exc.message : "Could not poll the job.");
      }
    };

    void tick();
    timer = window.setInterval(() => {
      void tick();
    }, POLL_MS);

    return () => {
      cancelled = true;
      stop();
    };
  }, [jobId]);

  async function submit(draft: DesignRequestDraft) {
    setError(null);
    setSubmitting(true);
    try {
      const accepted = await submitJob(toPayload(draft), draft.no_model);
      openedRef.current = false;
      jobIdRef.current = accepted.job_id;
      setJobId(accepted.job_id);
      setJob({
        job_id: accepted.job_id,
        request_id: accepted.request_id,
        status: accepted.status,
        phase: null,
        completed_phases: [],
        progress: null,
        activity: null,
        error: null,
        verdict: null,
        confidence: null,
      });
      return accepted.job_id;
    } catch (exc) {
      if (exc instanceof ApiError) setError(exc.message);
      else setError(exc instanceof Error ? exc.message : "Could not submit the job.");
      return null;
    } finally {
      setSubmitting(false);
    }
  }

  function attach(nextId: string) {
    if (jobIdRef.current === nextId) return;
    openedRef.current = false;
    jobIdRef.current = nextId;
    setError(null);
    setJobId(nextId);
    setJob({
      job_id: nextId,
      request_id: "",
      status: "running",
      phase: null,
      completed_phases: [],
      progress: null,
      activity: "Resuming job…",
      error: null,
      verdict: null,
      confidence: null,
    });
  }

  function reset() {
    openedRef.current = false;
    jobIdRef.current = null;
    setJobId(null);
    setJob(null);
    setError(null);
    setSubmitting(false);
  }

  return { job, error, submitting, submit, attach, reset, setError };
}
