import { useMemo, useState } from "react";
import { formatTokens, formatUsd, humanize } from "../../lib/format";
import type { LLMCall, PipelineTrace } from "../../types/trace";
import { EmptyValue } from "../ui";

function unique(values: Array<string | null>): string[] {
  return [...new Set(values.filter((value): value is string => Boolean(value)))].sort();
}

function CallRow({ call }: { call: LLMCall }) {
  const [open, setOpen] = useState(false);
  return (
    <article className="llm-row">
      <button type="button" className="llm-row-head" onClick={() => setOpen((value) => !value)}>
        <span className="mono">{call.call_id}</span>
        <span>{humanize(String(call.objective))}</span>
        <span>{humanize(String(call.stage ?? "unknown"))}</span>
        <span>{call.model}</span>
        <span>{formatTokens(call.input_tokens + call.output_tokens)}</span>
        <span>{formatUsd(call.cost_usd)}</span>
      </button>
      {open ? (
        <div className="llm-row-body">
          <p>
            Input {formatTokens(call.input_tokens)} · output {formatTokens(call.output_tokens)} ·{" "}
            {call.tool_calls.length} tools
          </p>
          {call.tool_calls.length === 0 ? (
            <EmptyValue />
          ) : (
            <ul className="stack-list">
              {call.tool_calls.map((tool, index) => (
                <li key={`${tool.tool}-${index}`}>
                  <strong>{tool.tool}</strong>
                  {tool.truncated ? " · truncated" : ""}
                  <pre className="mini-json">{JSON.stringify(tool.args, null, 2)}</pre>
                  <pre className="mini-json">{tool.result_snippet}</pre>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </article>
  );
}

export function LlmView({ trace }: { trace: PipelineTrace }) {
  const calls = trace.llm_calls;
  const stages = unique(calls.map((call) => (call.stage ? String(call.stage) : null)));
  const objectives = unique(calls.map((call) => String(call.objective)));
  const models = unique(calls.map((call) => call.model));
  const [stage, setStage] = useState("all");
  const [objective, setObjective] = useState("all");
  const [model, setModel] = useState("all");

  const filtered = useMemo(
    () =>
      calls.filter((call) => {
        if (stage !== "all" && call.stage !== stage) return false;
        if (objective !== "all" && call.objective !== objective) return false;
        if (model !== "all" && call.model !== model) return false;
        return true;
      }),
    [calls, stage, objective, model],
  );

  return (
    <div className="view-stack">
      <div className="filter-row">
        <label>
          Stage
          <select value={stage} onChange={(event) => setStage(event.target.value)}>
            <option value="all">All</option>
            {stages.map((item) => (
              <option key={item} value={item}>
                {humanize(item)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Objective
          <select value={objective} onChange={(event) => setObjective(event.target.value)}>
            <option value="all">All</option>
            {objectives.map((item) => (
              <option key={item} value={item}>
                {humanize(item)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Model
          <select value={model} onChange={(event) => setModel(event.target.value)}>
            <option value="all">All</option>
            {models.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        <p className="muted">{filtered.length} of {calls.length} calls</p>
      </div>
      {filtered.length === 0 ? (
        <EmptyValue />
      ) : (
        <div className="llm-table">
          <div className="llm-row-head llm-legend">
            <span>Call</span>
            <span>Objective</span>
            <span>Stage</span>
            <span>Model</span>
            <span>Tokens</span>
            <span>Cost</span>
          </div>
          {filtered.map((call, index) => (
            <CallRow key={`${call.call_id}-${index}`} call={call} />
          ))}
        </div>
      )}
    </div>
  );
}
