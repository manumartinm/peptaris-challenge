import { REQUIRED_TRACE_FIELDS, type PipelineTrace } from "../types/trace";
import { isRecord } from "./guards";
import { normalizeTrace } from "./normalize";

export interface ParseSuccess {
  ok: true;
  raw: unknown;
  text: string;
  trace: PipelineTrace;
}

export interface ParseFailure {
  ok: false;
  error: string;
}

export type ParseResult = ParseSuccess | ParseFailure;

function fieldLabel(path: string): string {
  return path;
}

export function parseTraceText(text: string): ParseResult {
  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch (error) {
    const detail = error instanceof Error ? error.message : "Unknown parse error";
    return {
      ok: false,
      error: `The file is not valid JSON (${detail}). Choose a PipelineTrace file such as REQ-01.trace.json.`,
    };
  }

  if (!isRecord(raw)) {
    return {
      ok: false,
      error: "The file must contain a single JSON object, not an array or primitive value.",
    };
  }

  const missing = REQUIRED_TRACE_FIELDS.filter((field) => raw[field] == null);
  if (missing.length > 0) {
    return {
      ok: false,
      error: `This JSON is missing required field${missing.length === 1 ? "" : "s"}: ${missing.map(fieldLabel).join(", ")}.`,
    };
  }

  if (!isRecord(raw.request)) {
    return { ok: false, error: "request must be an object with the design request." };
  }
  if (typeof raw.request.sequence !== "string" || raw.request.sequence.length === 0) {
    return { ok: false, error: "request.sequence is required and must be a non-empty string." };
  }
  if (!isRecord(raw.validation)) {
    return { ok: false, error: "validation must be an object." };
  }
  if (!isRecord(raw.tree)) {
    return { ok: false, error: "tree must be an object." };
  }
  if (!Array.isArray(raw.tree.nodes)) {
    return { ok: false, error: "tree.nodes must be an array of conflict nodes." };
  }
  if (!isRecord(raw.post_graph)) {
    return { ok: false, error: "post_graph must be an object." };
  }
  if (!isRecord(raw.verdict)) {
    return { ok: false, error: "verdict must be an object." };
  }
  if (typeof raw.verdict.verdict !== "string") {
    return { ok: false, error: "verdict.verdict is required." };
  }
  if (!isRecord(raw.cost)) {
    return { ok: false, error: "cost must be an object." };
  }
  if (raw.llm_calls != null && !Array.isArray(raw.llm_calls)) {
    return { ok: false, error: "llm_calls must be an array when present." };
  }
  if (raw.judge != null && !isRecord(raw.judge)) {
    return { ok: false, error: "judge must be an object when present." };
  }

  return {
    ok: true,
    raw,
    text,
    trace: normalizeTrace(raw),
  };
}

export async function parseTraceFile(file: File): Promise<ParseResult> {
  const text = await file.text();
  return parseTraceText(text);
}
