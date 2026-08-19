# 07 — Final judge, validation, confidence

**Purpose:** One pass over the winning candidate's whole trace. Look
for gaps earlier stages did not cover. Assign `confidence`. Verify
every citation before emit.

**Read this when:** you need what `confidence` means, or why a
citation was dropped.

**Prerequisites:** a winning leaf after [Intent](06-intent.md).
[Literature sandbox](11-literature-sandbox.md) for the persisted
cache `audit_ref` re-reads.

[Index](../plan.md)

---

## What this process does

One `final_judge` call over the whole trace of the winning candidate,
looking for gaps the earlier stages did not cover, and assigning
`confidence` against a fixed checklist:

| Signal | `confidence` |
|---|---|
| All provenance is `corpus`, zero degraded nodes, zero unmapped structurer spans, zero literature consulted | `high` |
| Any `inference` / `external` provenance, or a non-fatal degradation | `medium` |
| `insufficient_information`, or an unresolved gap touching an emitted conflict | `low` |

**Applied by the LLM as a literal checklist, for now**, not computed
directly. This is a known, flagged simplification; a model following
a rule can drift from it more than a fixed computation can, and
moving this into a deterministic check is the obvious upgrade if time
allows.

Confidence is a field of the CLI output
([Two outputs](09-outputs.md)). Verdict is still not written here.

---

## What this stage cannot do

No matter how a diagram draws it as one box: it cannot decide on its
own that a citation resolves.

`audit_ref` runs here too, but as a **deterministic check**, against
both workbooks by existing row and, for `external` citations, against
the persisted literature cache — no model call needed. If the LLM
trusts a citation `audit_ref` cannot verify, the check wins: the
citation degrades, never gets emitted.

That is axiom 5. Fabricating a corpus `ref` that does not support the
claim is the one unrecoverable error in the challenge. `score.py
--audit` checks reachability (workbook, sheet, content row), not
support. A human reads support. `audit_ref` at least makes
reachability a hard gate before emit.

`audit_ref` is also available mid-reasoning (unlimited budget) so the
model can self-correct before the emit gate.

prev: [Intent](06-intent.md) · [Index](../plan.md) · next: [The Agent](08-agent.md)
