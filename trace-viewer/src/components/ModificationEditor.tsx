import { MODIFICATION_FAMILIES } from "../constants/requestSchema";
import type { ModificationDraft } from "../lib/validateDesignRequest";
import { humanize } from "../lib/format";

interface ModificationEditorProps {
  modifications: ModificationDraft[];
  onChange: (next: ModificationDraft[]) => void;
}

export function ModificationEditor({ modifications, onChange }: ModificationEditorProps) {
  function update(index: number, patch: Partial<ModificationDraft>) {
    onChange(modifications.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)));
  }

  return (
    <div className="stack">
      {modifications.map((item, index) => (
        <div key={index} className="mod-row">
          <label>
            Family
            <select value={item.family} onChange={(event) => update(index, { family: event.target.value })}>
              {MODIFICATION_FAMILIES.map((family) => (
                <option key={family} value={family}>
                  {humanize(family)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Site
            <input
              value={item.site}
              onChange={(event) => update(index, { site: event.target.value })}
              placeholder="K12"
            />
          </label>
          <label className="grow">
            Detail
            <input
              value={item.detail}
              onChange={(event) => update(index, { detail: event.target.value })}
              placeholder="optional"
            />
          </label>
          <button
            type="button"
            className="ghost-button dark"
            onClick={() => onChange(modifications.filter((_, itemIndex) => itemIndex !== index))}
            disabled={modifications.length === 1}
          >
            Remove
          </button>
        </div>
      ))}
      <button
        type="button"
        className="ghost-button dark"
        onClick={() => onChange([...modifications, { family: "lipidation", site: "", detail: "" }])}
      >
        Add modification
      </button>
    </div>
  );
}
