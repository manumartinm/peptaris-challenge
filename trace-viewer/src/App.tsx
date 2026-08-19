import { useCallback, useEffect, useRef, useState } from "react";
import { ErrorBanner } from "./components/ErrorBanner";
import { Header } from "./components/Header";
import { LaunchView } from "./components/LaunchView";
import { TabBar } from "./components/TabBar";
import { IntentView } from "./components/views/IntentView";
import { JudgeView } from "./components/views/JudgeView";
import { JsonView } from "./components/views/JsonView";
import { LlmView } from "./components/views/LlmView";
import { MolecularView } from "./components/views/MolecularView";
import { SummaryView } from "./components/views/SummaryView";
import { TreeView } from "./components/views/TreeView";
import { ValidateView } from "./components/views/ValidateView";
import { useAppRoute } from "./hooks/useAppRoute";
import { usePipelineJob } from "./hooks/usePipelineJob";
import { ApiError, fetchJob, fetchJobTrace, fetchStoredTraces } from "./lib/api";
import { isRecord } from "./lib/guards";
import { parseTraceFile, parseTraceText } from "./lib/parseTrace";
import { parseRoute, serializeRoute } from "./lib/routes";
import { createDraft, type DesignRequestDraft } from "./lib/validateDesignRequest";
import type { TabId } from "./types/tabs";
import type { PipelineTrace } from "./types/trace";

interface LoadedTrace {
  fileName: string;
  trace: PipelineTrace;
  raw: unknown;
  jobId: string | null;
}

function requestIdFromRaw(raw: unknown, fallback: string): string {
  if (isRecord(raw) && typeof raw.request_id === "string" && raw.request_id) {
    return raw.request_id;
  }
  return fallback;
}

export default function App() {
  const { route, go } = useAppRoute();
  const [loaded, setLoaded] = useState<LoadedTrace | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<TabId>("home");
  const [draft, setDraft] = useState<DesignRequestDraft>(createDraft);
  const [openingJobId, setOpeningJobId] = useState<string | null>(null);
  const loadedJobIdRef = useRef<string | null>(null);

  loadedJobIdRef.current = loaded?.jobId ?? null;

  const applyTrace = useCallback((raw: unknown, requestId: string, jobId: string | null) => {
    const result = parseTraceText(JSON.stringify(raw));
    if (!result.ok) {
      setError(result.error);
      return false;
    }
    setLoaded({
      fileName: `${requestId}.trace.json`,
      trace: result.trace,
      raw: result.raw,
      jobId,
    });
    document.title = `${requestId} · Trace Explorer`;
    return true;
  }, []);

  const pipeline = usePipelineJob((raw, requestId, jobId) => {
    if (!applyTrace(raw, requestId, jobId)) return;
    go({ kind: "job", jobId, tab: "home" }, "replace");
  });

  const openTab = useCallback(
    (next: TabId) => {
      setTab(next);
      if (route.kind === "job") go({ kind: "job", jobId: route.jobId, tab: next }, "replace");
      if (route.kind === "request") {
        go({ kind: "request", requestId: route.requestId, tab: next }, "replace");
      }
    },
    [go, route],
  );

  const routeKey =
    route.kind === "job"
      ? `job:${route.jobId}`
      : route.kind === "request"
        ? `request:${route.requestId}`
        : "home";
  const activeTab = route.kind === "job" || route.kind === "request" ? route.tab : tab;
  const pipelineRef = useRef(pipeline);
  pipelineRef.current = pipeline;
  const goRef = useRef(go);
  goRef.current = go;

  useEffect(() => {
    if (routeKey === "home") {
      if (loadedJobIdRef.current) {
        setLoaded(null);
        pipelineRef.current.reset();
        setTab("home");
        document.title = "Trace Explorer · De la Fuente Lab";
      }
      return;
    }

    let cancelled = false;
    const current = parseRoute(window.location);

    async function restore() {
      if (current.kind === "request") {
        try {
          const listed = await fetchStoredTraces();
          const match = listed.traces.find((item) => item.request_id === current.requestId);
          if (cancelled) return;
          if (!match) {
            setError(`No stored trace for ${current.requestId}.`);
            return;
          }
          goRef.current({ kind: "job", jobId: match.job_id, tab: current.tab }, "replace");
        } catch (exc) {
          if (!cancelled) {
            setError(exc instanceof Error ? exc.message : "Could not resolve that request.");
          }
        }
        return;
      }

      if (current.kind !== "job") return;
      const jobId = current.jobId;
      if (loadedJobIdRef.current === jobId) return;
      const live = pipelineRef.current.job;
      if (
        live?.job_id === jobId &&
        (live.status === "queued" || live.status === "running")
      ) {
        return;
      }

      setOpeningJobId(jobId);
      setError(null);
      try {
        try {
          const job = await fetchJob(jobId);
          if (cancelled) return;
          if (job.status === "queued" || job.status === "running" || job.status === "failed") {
            pipelineRef.current.attach(jobId);
            if (job.status === "failed") setError(job.error || "The job failed.");
            return;
          }
        } catch {
          // Job is no longer in memory; open the file on disk if it exists.
        }
        const raw = await fetchJobTrace(jobId);
        if (cancelled) return;
        applyTrace(raw, requestIdFromRaw(raw, jobId), jobId);
      } catch (exc) {
        if (cancelled) return;
        if (exc instanceof ApiError) setError(exc.message);
        else setError(exc instanceof Error ? exc.message : "Could not open the trace.");
      } finally {
        if (!cancelled) setOpeningJobId(null);
      }
    }

    void restore();
    return () => {
      cancelled = true;
    };
  }, [applyTrace, routeKey]);

  function startFresh() {
    setLoaded(null);
    setError(null);
    setTab("home");
    pipeline.reset();
    setDraft(createDraft());
    document.title = "Trace Explorer · De la Fuente Lab";
    go({ kind: "home" }, "push");
  }

  async function handleFile(file: File) {
    setBusy(true);
    setError(null);
    const result = await parseTraceFile(file);
    setBusy(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setLoaded({ fileName: file.name, trace: result.trace, raw: result.raw, jobId: null });
    setTab("home");
    document.title = `${file.name} · Trace Explorer`;
    go({ kind: "home" }, "replace");
  }

  const linkHref =
    loaded?.jobId && route.kind === "job" ? serializeRoute(route) : null;

  return (
    <div className={loaded ? "app app-loaded" : "app"}>
      <Header
        fileName={loaded?.fileName ?? null}
        linkHref={linkHref}
        onHome={startFresh}
        onNewRequest={startFresh}
      />
      {error ? <ErrorBanner message={error} onDismiss={() => setError(null)} /> : null}
      {loaded ? (
        <>
          <TabBar active={activeTab} onChange={openTab} />
          <main className={activeTab === "walk" ? "workspace workspace-tree" : "workspace"}>
            {activeTab === "home" ? <SummaryView trace={loaded.trace} onOpen={openTab} /> : null}
            {activeTab === "validate" ? <ValidateView trace={loaded.trace} /> : null}
            {activeTab === "walk" ? <TreeView trace={loaded.trace} /> : null}
            {activeTab === "molecular" ? <MolecularView trace={loaded.trace} /> : null}
            {activeTab === "intent" ? <IntentView trace={loaded.trace} /> : null}
            {activeTab === "judge" ? <JudgeView trace={loaded.trace} /> : null}
            {activeTab === "llm" ? <LlmView trace={loaded.trace} /> : null}
            {activeTab === "json" ? <JsonView raw={loaded.raw} /> : null}
          </main>
        </>
      ) : (
        <main className="empty-shell">
          <LaunchView
            draft={draft}
            job={pipeline.job}
            submitting={pipeline.submitting}
            busyFile={busy}
            formError={pipeline.error}
            onDraftChange={setDraft}
            onSubmit={() => {
              void pipeline.submit(draft).then((jobId) => {
                if (jobId) go({ kind: "job", jobId, tab: "home" }, "push");
              });
            }}
            onFile={handleFile}
            onOpenStored={(jobId) => {
              go({ kind: "job", jobId, tab: "home" }, "push");
            }}
            openingJobId={openingJobId}
            onRetry={() => pipeline.reset()}
          />
        </main>
      )}
    </div>
  );
}
