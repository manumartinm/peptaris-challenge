# 09 — Two outputs

**Purpose:** The schema-exact CLI object and a separate internal
trace. This process writes `verdict`. Nothing earlier does.

**Read this when:** you need what the two files contain, or which
process produced which field.

**Prerequisites:** winning leaf, `confidence`, accumulated findings.
[Operational rules](12-operational-rules.md) for how `verdict` and
`conflicts[]` are derived.

[Index](../plan.md)

---

## 8.1 CLI output (schema-exact)

`data/schema.json` is authoritative. Shape:

```json
{
  "request_id": "REQ-05",
  "verdict": "feasible | feasible_with_changes | infeasible | insufficient_information",
  "confidence": "high | medium | low",
  "resolved_sequence": "...",
  "resolved_annotations": {"X27": "Nle"},
  "site_map": [{"requested": "K5", "resolved": "K5", "residue": "Lys", "note": null}],
  "route": [{"step": 1, "stage": "resin_selection", "operation": "...",
             "provenance": [{"kind": "corpus", "ref": "..."}]}],
  "conflicts": [{"severity": "blocking | major | minor",
                 "kind": "...", "description": "...", "affected": ["K5"],
                 "resolution": "concrete alternative, or null if none exists",
                 "provenance": [{"kind": "corpus", "ref": "..."}]}],
  "unknowns": ["..."]
}
```

| Field | Produced by |
|---|---|
| `verdict` | The ladder, over the winning leaf's accumulated findings. No other component writes this |
| `confidence` | [Final judge](07-final-judge.md) checklist |
| `resolved_sequence`, `resolved_annotations` | [Validation Engine](03-validation-engine.md), fixed once |
| `site_map` | Validation Engine, over `modifications` only, never `parent_features` |
| `route` | [Conflict detection](04-conflict-detection.md) backward walk plus the deterministic tail |
| `conflicts` | One consolidated entry per branch point that needed more than the first candidate, not one per failed attempt |
| `unknowns` | Any degraded node, any genuine tie, any topic molecular validation / intent / judge could not anchor |

`kind` must be one of: `protecting_group_orthogonality` ·
`order_of_operations` · `mutually_exclusive` · `site_invalid` ·
`reagent_incompatibility` · `building_block_availability` ·
`intent_not_achieved`. Anything else is `unreadable_conflict_kinds`.

Severity and verdict are coupled. A `major` or `blocking` conflict is
incompatible with `verdict: feasible`. A `blocking` one requires a
refusal verdict. Choosing a resin or a protecting group in the first
place is designing the route, not changing it.

The schema forbids extra top-level fields.

---

## 8.2 Trace output (internal)

One file per request, never fed to `score.py`:
`traces/{request_id}.trace.json`.

Serializes the full tree, every `State`, every `LLMCall` and its
`tool_calls`, `result_snippet` truncated to 500 characters by default
with a `truncated` flag.

Reports token and call counts as the headline metric per request,
median and worst case. Cost in USD stays internal only; the spec asks
for counts, not dollars.

prev: [The Agent](08-agent.md) · [Index](../plan.md) · next: [Family profiles](10-extracted-families.md)
