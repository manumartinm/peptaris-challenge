# 10 — `extracted_families.json`: the only offline artifact

**Purpose:** One corpus-derived file the runtime reads. Built once,
checkpointed, cited by `ref_row`. No second derived table is
persisted.

**Read this when:** you need what a family profile contains, or what
ablation A would strip.

**Prerequisites:** the 15 family tabs in
`ApexChem_Synthesis_Reactions_by_AminoAcid.xlsx`.

[Index](../plan.md)

---

## What this process produces

Built once, from the 15 family tabs. One extraction call per tab (or
per discovered process), every chemical field checked against the
workbook before acceptance. Checkpointed (`REFRESH_EXTRACTION`,
default `False`) so a later change to how it's consumed does not
re-pay those calls.

The model may synthesize only labels (`name`, `summary`,
`when_to_use`). Every chemical field comes from workbook cells.
Invalid row or column references are rejected.

The runtime view `check_compatibility` needs:

```
family_profiles["lipidation"] = {
  "requires": [...], "reagents": [{"condition": "1% TFA/DCM", "ref_row": 8}, ...],
  "explicit_risks": [{"text": "...", "ref_row": 24}, ...],
  "explicit_alternatives": [{"text": "...", "ref_row": 25}, ...],
  "stage_hint": "on_resin_modification",
  "building_blocks": [...],
}
```

The file on disk is schema `2.0.0`: each family has a `processes` map
(Mtt vs ivDde vs Alloc are separate processes, not flattened category
lists). `family_profile_lookup` projects a process — not a whole
family — into the view above, so risks of Alloc are not attributed to
Mtt.

**No second, derived, persisted table exists.** `check_compatibility`
reads this file directly, through `family_profile_lookup`, cached by
the signature in [Conflict detection](04-conflict-detection.md). This
is the one deliberate simplification from earlier drafts: what used
to be a pre-computed cross-table is now a live, cached Agent call,
traded for less offline engineering at the cost of a
per-novel-candidate call instead of a free lookup.

Sparse `explicit_alternatives` means the tree cannot propose siblings.

Ablation A strips this file, the tool's access to it, and any corpus
text embedded in the system prompt. See
[Spec corrections](13-spec-corrections.md).

---

## Families (tab order)

`spps_foundation` · `special_residues` · `n_methylation` ·
`c_term_amidation` · `n_term_acetylation` · `lipidation` ·
`pegylation` · `glycosylation` · `cyclization` ·
`hydrocarbon_stapling` · `disulfide` · `biaryl_bisalkylation` ·
`aza_peptide` · `retro_inverso` · `charge_hybrids`

These map onto corpus tabs `01_` … `15_` in that order.

prev: [Two outputs](09-outputs.md) · [Index](../plan.md) · next: [Literature sandbox](11-literature-sandbox.md)
