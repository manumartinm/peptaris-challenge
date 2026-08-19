# 08 — The Agent: one implementation, three objectives

**Purpose:** One system-prompt skeleton, one tool list, a different
`objective` string per call. The Agent never writes `verdict` and
never edits the request.

**Read this when:** you need what each objective may produce, or which
tools exist.

**Prerequisites:** [Base types](02-base-types.md) `LLMCall`. Call
sites: [Conflict detection](04-conflict-detection.md),
[Intent](06-intent.md), [Final judge](07-final-judge.md).

[Index](../plan.md)

---

## Contract

Same system prompt skeleton, same tool list, a different `objective`
string per call.

| `objective` | Called from | Can produce |
|---|---|---|
| `check_compatibility` | Conflict detection, per candidate | pass/fail, and an alternative candidate if it fails |
| `check_intent` | Intent, per surviving candidate | `intent_not_achieved`, or nothing |
| `final_judge` | Final judge, once | gaps, `confidence` |

**Hard contract, unconditional:** the Agent never writes `verdict`. It
never touches `modifications`, `sequence`, or any other field of the
original request. The only thing it may propose is a `resolution`
achieving the same modification at the same site.

Literature fetch is a separate orchestration
([Literature sandbox](11-literature-sandbox.md)), not a chemistry
loop. Chemistry judgment is these three calls.

There is no critic-and-proposer loop. Detect-and-propose is already
one `check_compatibility` turn.

---

## Tools available to every Agent call

Regardless of objective:

| Tool | Reads | Budget |
|---|---|---|
| `family_profile_lookup` | `extracted_families.json`, cited by `ref_row` | Unlimited |
| `lookup_target` | `targets.xlsx`, only used by `check_intent` | Unlimited |
| `search_literature` | Real web search, scoped to peptide-chemistry journals | 3 per invocation |
| `fetch_and_parse` | Parses and persists to the sandbox | 2 per invocation |
| `audit_ref` | Mid-reasoning self-correction, and as the final gate | Unlimited |

`lookup_target` is on the shared list so the tool belt stays one;
`check_compatibility` and `final_judge` should not need it.

Caching for compatibility is keyed on
`(candidate_process, candidate_site, frozenset(state_categories_present))`,
never on `request_id`. See [Conflict detection](04-conflict-detection.md).

Every call is recorded as an `LLMCall` on the `State` that triggered
it, including `tool_calls` with `result_snippet` truncated to 500
characters and a `truncated` flag.

prev: [Final judge](07-final-judge.md) · [Index](../plan.md) · next: [Two outputs](09-outputs.md)
