import { useMemo, useState, type ReactNode } from "react";

function highlight(text: string, query: string): ReactNode {
  if (!query) return text;
  const index = text.toLowerCase().indexOf(query.toLowerCase());
  if (index === -1) return text;
  return (
    <>
      {text.slice(0, index)}
      <mark>{text.slice(index, index + query.length)}</mark>
      {text.slice(index + query.length)}
    </>
  );
}

function matchesQuery(value: unknown, query: string): boolean {
  if (!query) return true;
  const needle = query.toLowerCase();
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value).toLowerCase().includes(needle);
  }
  if (value == null) return false;
  if (Array.isArray(value)) return value.some((item) => matchesQuery(item, query));
  if (typeof value === "object") {
    return Object.entries(value).some(
      ([key, item]) => key.toLowerCase().includes(needle) || matchesQuery(item, query),
    );
  }
  return false;
}

function JsonNode({
  name,
  value,
  query,
  depth,
}: {
  name: string;
  value: unknown;
  query: string;
  depth: number;
}) {
  const [open, setOpen] = useState(depth < 2 || Boolean(query && matchesQuery(value, query)));
  const isObject = value !== null && typeof value === "object";

  if (!isObject) {
    return (
      <div className="json-line" style={{ paddingLeft: depth * 16 }}>
        <span className="json-key">{highlight(name, query)}</span>
        <span className="json-colon">: </span>
        <span className="json-value">{highlight(JSON.stringify(value), query)}</span>
      </div>
    );
  }

  const entries = Array.isArray(value)
    ? value.map((item, index) => [String(index), item] as const)
    : Object.entries(value);
  const visible = query
    ? entries.filter(
        ([key, item]) =>
          key.toLowerCase().includes(query.toLowerCase()) || matchesQuery(item, query),
      )
    : entries;

  return (
    <div className="json-block">
      <button
        type="button"
        className="json-toggle"
        style={{ paddingLeft: depth * 16 }}
        onClick={() => setOpen((current) => !current)}
      >
        <span className="json-chevron">{open ? "▾" : "▸"}</span>
        <span className="json-key">{highlight(name, query)}</span>
        <span className="muted">
          {Array.isArray(value) ? `[${value.length}]` : `{${entries.length}}`}
        </span>
      </button>
      {open
        ? visible.map(([key, item]) => (
            <JsonNode key={key} name={key} value={item} query={query} depth={depth + 1} />
          ))
        : null}
    </div>
  );
}

export function JsonView({ raw }: { raw: unknown }) {
  const [query, setQuery] = useState("");
  const hasMatch = useMemo(() => matchesQuery(raw, query), [raw, query]);

  return (
    <div className="json-view">
      <div className="filter-row">
        <label className="grow">
          Search
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Find a key, site, process, or citation"
          />
        </label>
      </div>
      {query && !hasMatch ? (
        <p className="muted">No keys or values match that search.</p>
      ) : (
        <div className="json-tree">
          <JsonNode key={query || "trace"} name="trace" value={raw} query={query} depth={0} />
        </div>
      )}
    </div>
  );
}
