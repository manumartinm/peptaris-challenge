import { MODIFICATION_FAMILIES, PARENT_C_TERMINI, STANDARD_LETTERS } from "../constants/requestSchema";
import type { DesignRequestPayload } from "../types/job";

export interface ModificationDraft {
  family: string;
  site: string;
  detail: string;
}

export interface AnnotationDraft {
  key: string;
  value: string;
}

export interface DesignRequestDraft {
  request_id: string;
  parent_name: string;
  sequence: string;
  parent_c_terminus: string;
  residue_annotations: AnnotationDraft[];
  parent_features: string;
  modifications: ModificationDraft[];
  intent: string;
  no_model: boolean;
}

export function createDraft(): DesignRequestDraft {
  return {
    request_id: `REQ-${crypto.randomUUID().slice(0, 8).toUpperCase()}`,
    parent_name: "",
    sequence: "",
    parent_c_terminus: "free_acid",
    residue_annotations: [],
    parent_features: "",
    modifications: [{ family: "lipidation", site: "", detail: "" }],
    intent: "",
    no_model: false,
  };
}

export function validateDesignRequest(draft: DesignRequestDraft): string[] {
  const errors: string[] = [];
  if (!draft.request_id.trim()) errors.push("request_id is required.");
  if (!draft.parent_name.trim()) errors.push("parent_name is required.");
  if (!draft.sequence.trim()) errors.push("sequence is required.");
  if (!PARENT_C_TERMINI.includes(draft.parent_c_terminus as (typeof PARENT_C_TERMINI)[number])) {
    errors.push("parent_c_terminus must be free_acid, amide, or alcohol.");
  }
  if (!draft.intent.trim()) errors.push("intent is required.");

  const sequence = draft.sequence.trim().toUpperCase();
  const annotations = Object.fromEntries(
    draft.residue_annotations
      .filter((item) => item.key.trim())
      .map((item) => [item.key.trim(), item.value.trim()]),
  );
  const missingX: string[] = [];
  for (let index = 0; index < sequence.length; index += 1) {
    const letter = sequence[index];
    if (letter === "X") {
      const key = `X${index + 1}`;
      if (!annotations[key]) missingX.push(key);
    } else if (!STANDARD_LETTERS.includes(letter)) {
      errors.push(`sequence[${index + 1}]=${letter} is outside the standard alphabet.`);
    }
  }
  if (missingX.length > 0) {
    errors.push(`every X must be declared in residue_annotations; missing ${missingX.join(", ")}.`);
  }

  const modifications = draft.modifications.filter((item) => item.family || item.site || item.detail);
  if (modifications.length === 0) errors.push("at least one modification is required.");
  for (const modification of modifications) {
    if (!MODIFICATION_FAMILIES.includes(modification.family as (typeof MODIFICATION_FAMILIES)[number])) {
      errors.push(`unknown modification family: ${modification.family || "(empty)"}.`);
    }
    if (!modification.site.trim()) errors.push("each modification needs a site.");
  }
  return errors;
}

export function toPayload(draft: DesignRequestDraft): DesignRequestPayload {
  const annotations: Record<string, string> = {};
  for (const item of draft.residue_annotations) {
    if (item.key.trim()) annotations[item.key.trim()] = item.value.trim();
  }
  return {
    request_id: draft.request_id.trim(),
    parent_name: draft.parent_name.trim(),
    sequence: draft.sequence.trim().toUpperCase(),
    parent_c_terminus: draft.parent_c_terminus as DesignRequestPayload["parent_c_terminus"],
    residue_annotations: annotations,
    parent_features: draft.parent_features
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean),
    modifications: draft.modifications
      .filter((item) => item.family && item.site.trim())
      .map((item) => ({
        family: item.family,
        site: item.site.trim(),
        detail: item.detail.trim() ? item.detail.trim() : null,
      })),
    intent: draft.intent.trim(),
  };
}
