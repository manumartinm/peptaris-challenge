# 13 — Spec corrections, updated

**Purpose:** The one wording change now that the conflict matrix is
gone. Every other point on the original corrections list still holds.

**Read this when:** you need what ablation A strips, or where
`conflict_matrix.json` went.

**Prerequisites:** [Family profiles](10-extracted-families.md).
[System overview](00-overview.md).

[Index](../plan.md)

---

## Point 7 — ablation A boundary

Earlier drafts said:

> `conflict_matrix.json` and `family_pair_cache.json` are exactly the
> kind of corpus-derived artifacts ablation would have to strip.

**Current wording:** ablation A would have to strip
`extracted_families.json` itself, the `family_profile_lookup` tool's
access to it, and any corpus text embedded in the Agent's system
prompt, keeping only sequence parsing, index arithmetic, and schema
validation. Defining that boundary cleanly is still awkward for this
architecture, which is still the spec's own sanctioned reason to say
so in `EVAL_REPORT.md` rather than forcing a number.

The challenge's definition of A, for reference: the identical
pipeline with every corpus-derived **artifact** removed — prompt text
and any hand-transcribed table, index or rule derived from the
workbook — keeping the request, the schema, the model, and only
operations that encode no corpus content.

---

## What still holds

- Ablation B (no-model) is required. Report it twice: deterministic
  layer on, and off. The stub returns `feasible / high / conflicts: []`.
- `data/score.py` is the scorer.
- Each self-written eval case exists before the first run against it.
  If a case is wrong after a run, it is referred, not revised.
- `score.py --audit` takes **both** workbooks.
- Clean-clone check and README are not cuttable.

prev: [Operational rules](12-operational-rules.md) · [Index](../plan.md) · next: [Three-day order](14-three-day-order.md)
