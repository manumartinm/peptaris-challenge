export const JOB_PHASES = [
  "validate",
  "walk",
  "molecular",
  "intent",
  "judge",
  "assemble",
] as const;

export type JobPhase = (typeof JOB_PHASES)[number];
export type JobStatusName = "queued" | "running" | "completed" | "failed";

export interface JobProgress {
  current: number | null;
  total: number | null;
  label: string | null;
}

export interface JobState {
  job_id: string;
  request_id: string;
  status: JobStatusName;
  phase: JobPhase | null;
  completed_phases: JobPhase[];
  progress: JobProgress | null;
  activity: string | null;
  error: string | null;
  verdict: string | null;
  confidence: string | null;
}

export interface JobAccepted {
  job_id: string;
  status: JobStatusName;
  request_id: string;
}

export interface StoredTrace {
  job_id: string;
  request_id: string;
  file_name: string;
  parent_name: string | null;
  verdict: string | null;
  confidence: string | null;
  modified_at: string;
}

export interface StoredTraceList {
  traces: StoredTrace[];
}

export interface DesignRequestPayload {
  request_id: string;
  parent_name: string;
  sequence: string;
  parent_c_terminus: "free_acid" | "amide" | "alcohol";
  residue_annotations: Record<string, string>;
  parent_features: string[];
  modifications: Array<{
    family: string;
    site: string;
    detail: string | null;
  }>;
  intent: string;
}
