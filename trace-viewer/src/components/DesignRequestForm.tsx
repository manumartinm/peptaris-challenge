import { PARENT_C_TERMINI } from "../constants/requestSchema";
import { humanize } from "../lib/format";
import type { DesignRequestDraft } from "../lib/validateDesignRequest";
import { ModificationEditor } from "./ModificationEditor";

interface DesignRequestFormProps {
  draft: DesignRequestDraft;
  errors: string[];
  submitting: boolean;
  onChange: (draft: DesignRequestDraft) => void;
  onSubmit: () => void;
}

export function DesignRequestForm({
  draft,
  errors,
  submitting,
  onChange,
  onSubmit,
}: DesignRequestFormProps) {
  return (
    <form
      className="request-form"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <div className="form-grid">
        <label>
          Request ID
          <input
            value={draft.request_id}
            onChange={(event) => onChange({ ...draft, request_id: event.target.value })}
          />
        </label>
        <label>
          Parent peptide
          <input
            value={draft.parent_name}
            onChange={(event) => onChange({ ...draft, parent_name: event.target.value })}
            placeholder="glucagon"
          />
        </label>
        <label>
          C-terminus
          <select
            value={draft.parent_c_terminus}
            onChange={(event) => onChange({ ...draft, parent_c_terminus: event.target.value })}
          >
            {PARENT_C_TERMINI.map((item) => (
              <option key={item} value={item}>
                {humanize(item)}
              </option>
            ))}
          </select>
        </label>
      </div>
      <label>
        Sequence
        <textarea
          className="mono"
          rows={3}
          value={draft.sequence}
          onChange={(event) => onChange({ ...draft, sequence: event.target.value })}
          placeholder="HSQGTFTSDYSKYLDSRRAQDFVQWLMNT"
        />
      </label>
      <label>
        Intent
        <textarea
          rows={2}
          value={draft.intent}
          onChange={(event) => onChange({ ...draft, intent: event.target.value })}
          placeholder="extend plasma half-life via albumin binding"
        />
      </label>
      <fieldset>
        <legend>Modifications</legend>
        <ModificationEditor
          modifications={draft.modifications}
          onChange={(modifications) => onChange({ ...draft, modifications })}
        />
      </fieldset>
      <details className="advanced">
        <summary>Advanced fields</summary>
        <label>
          Residue annotations
          <p className="muted">Required for every X in the sequence, as X12: description.</p>
        </label>
        {draft.residue_annotations.map((item, index) => (
          <div key={index} className="mod-row">
            <input
              value={item.key}
              placeholder="X12"
              onChange={(event) => {
                const next = draft.residue_annotations.map((entry, entryIndex) =>
                  entryIndex === index ? { ...entry, key: event.target.value } : entry,
                );
                onChange({ ...draft, residue_annotations: next });
              }}
            />
            <input
              className="grow-input"
              value={item.value}
              placeholder="description"
              onChange={(event) => {
                const next = draft.residue_annotations.map((entry, entryIndex) =>
                  entryIndex === index ? { ...entry, value: event.target.value } : entry,
                );
                onChange({ ...draft, residue_annotations: next });
              }}
            />
          </div>
        ))}
        <button
          type="button"
          className="ghost-button dark"
          onClick={() =>
            onChange({
              ...draft,
              residue_annotations: [...draft.residue_annotations, { key: "", value: "" }],
            })
          }
        >
          Add annotation
        </button>
        <label>
          Parent features
          <input
            value={draft.parent_features}
            onChange={(event) => onChange({ ...draft, parent_features: event.target.value })}
            placeholder="comma-separated, optional"
          />
        </label>
      </details>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={draft.no_model}
          onChange={(event) => onChange({ ...draft, no_model: event.target.checked })}
        />
        Skip live model calls
      </label>
      {errors.length > 0 ? (
        <ul className="form-errors">
          {errors.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : null}
      <button type="submit" className="primary-button" disabled={submitting}>
        {submitting ? "Submitting…" : "Submit job"}
      </button>
    </form>
  );
}
