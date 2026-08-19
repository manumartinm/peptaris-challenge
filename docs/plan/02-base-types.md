# 02 — Base types

**Purpose:** The frozen records every later process writes and reads.
Later pages assume the field names below.

**Read this when:** asking what a node carries, or whether it touched
the model.

**Prerequisites:** [Axioms](01-axioms.md) 4 and 5.

[Index](../plan.md)

---

## Types

```python
from dataclasses import dataclass
from typing import Literal

@dataclass(frozen=True)
class Error:
    check: str
    input_snapshot: dict
    expected: str
    got: str
    ref: str | None
    message: str

@dataclass(frozen=True)
class Provenance:
    kind: Literal["corpus", "inference", "external"]
    ref: str | None
    refs: list[str] | None
    source: str | None        # DOI/URL/citation, NOT "url" (schema field name)
    basis: str | None

@dataclass(frozen=True)
class ToolCall:
    tool: str
    args: dict
    result_snippet: str
    truncated: bool

@dataclass(frozen=True)
class LLMCall:
    call_id: str
    model: str
    objective: Literal["check_compatibility", "check_intent", "final_judge"]
    input_tokens: int
    output_tokens: int
    cost_usd: float
    cache: dict                    # {"key": str, "hit": bool}
    tool_calls: list[ToolCall]

@dataclass(frozen=True)
class Bond:
    from_atom: str
    to_fragment: str
    bond_type: str                 # "amide", "disulfide", "thioether", ...

@dataclass(frozen=True)
class State:
    id: str
    node_type: str
    parents: tuple[str, ...]
    modification_ref: int | None   # index into request.modifications, or None
    status: Literal["pass", "fail", "degraded"]
    output: dict                   # short labels, cheap to compare
    building_block: str | None     # exact reagent string tried here, if any
    sequence_snapshot: str | None  # human-readable render of the whole chain here
    route_step: dict | None        # what this node commits to route, or None
    errors: list[Error]
    provenance: list[Provenance]
    llm_calls: list[LLMCall]       # [] on every pure-code node, never absent
```

`llm_calls` is always present, empty or not. That single rule is what
lets you ask "how many nodes in this tree touched the model" with one
query instead of checking for a missing field.

---

## Field rules that later processes depend on

| Field | Rule |
|---|---|
| `parents` | Immutable lineage. A node is never edited; a new child points back. |
| `modification_ref` | Index into `request.modifications`, or `None` for resin / bulk assembly / tail steps. |
| `output` | Short labels only. `output["protected"]` is the cheap ledger for `check_compatibility`. |
| `building_block` | Exact `Fmoc-...-OH` string from `extracted_families.json`, pass or fail, never reconstructed from the short label. |
| `sequence_snapshot` | Human-readable only. Never parsed back by any check. |
| `route_step` | `None` on a failed candidate. Surviving nodes may commit one step. |
| `llm_calls` | `[]` on every pure-code node. Never omit the field. |

`output["permanent_connectivity"]` is a growing tuple of `Bond`. Only
bonds that survive to the final product. A node that only swaps a
temporary cap does not append here. See
[Conflict detection § two ledgers](04-conflict-detection.md).

The CLI object (`RouteVerdict`) is a different shape from `State`.
`State` is the internal tree node. They are not the same record.

prev: [Axioms](01-axioms.md) · [Index](../plan.md) · next: [Validation Engine](03-validation-engine.md)
