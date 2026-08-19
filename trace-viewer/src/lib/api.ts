import type {
  DesignRequestPayload,
  JobAccepted,
  JobState,
  StoredTraceList,
} from "../types/job";
import { isRecord } from "./guards";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function readError(response: Response): Promise<string> {
  const body: unknown = await response.json().catch(() => null);
  if (!isRecord(body)) return response.statusText || `HTTP ${response.status}`;
  const detail = body.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (!isRecord(item)) return String(item);
        const loc = Array.isArray(item.loc) ? item.loc.slice(1).join(".") : "";
        const msg = typeof item.msg === "string" ? item.msg : "invalid";
        return loc ? `${loc}: ${msg}` : msg;
      })
      .join("; ");
  }
  return response.statusText || `HTTP ${response.status}`;
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    throw new ApiError(await readError(response), response.status);
  }
  return (await response.json()) as T;
}

export async function fetchHealth(): Promise<Record<string, unknown>> {
  return requestJson("/api/health");
}

export async function submitJob(
  payload: DesignRequestPayload,
  noModel: boolean,
): Promise<JobAccepted> {
  const query = noModel ? "?no_model=true" : "";
  return requestJson(`/api/jobs${query}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function fetchJob(jobId: string): Promise<JobState> {
  return requestJson(`/api/jobs/${jobId}`);
}

export async function fetchJobTrace(jobId: string): Promise<unknown> {
  return requestJson(`/api/jobs/${jobId}/trace`);
}

export async function fetchStoredTraces(): Promise<StoredTraceList> {
  return requestJson("/api/traces");
}
