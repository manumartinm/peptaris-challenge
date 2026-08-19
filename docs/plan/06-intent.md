# 06 — Modified sequences + intent

**Purpose:** Ask whether the surviving chemistry still achieves the
design goal. This is the only process that may produce
`intent_not_achieved`. It is also the only process that reads
`ApexChem_templates_and_targets.xlsx`.

**Read this when:** you need what `check_intent` may produce, or which
of two chemistry survivors wins.

**Prerequisites:** [Conflict detection](04-conflict-detection.md)
survivors that passed the [Molecular validation](05-molecular-validation.md)
2D gate. Descriptor and 3D-ensemble numbers if those blocks ran.

[Index](../plan.md)

---

## What this process does

One `check_intent` call per **2D-valid** surviving candidate.
`ApexChem_templates_and_targets.xlsx` enters the system **only
here**, nowhere else: not the Validation Engine, not candidate
generation, not `check_compatibility`.

It supplies:

- receptor and ligand role
- invariant windows when the workbook actually has them
- SAR precedents when the workbook actually has them
- a small hand-authored table of receptor-class-level heuristics
  (GPCR class A vs class B1's two-domain binding vs
  guanylate-cyclase-type), because class-level pharmacology
  generalizes better than any single sibling precedent

Missing workbook rows, missing SAR columns, or an unparseable display
sequence are `unknowns`. They are not invented windows.

The only kind this call can produce is `intent_not_achieved`, or
nothing. Other finding kinds are dropped. It never writes `route`,
never writes `site_map`, never changes which candidate survived the
tree.

Read `intent` as the design goal, not as a literal string to satisfy.
"Improve solubility" is met by any PEG, but if that PEG lands on the
pharmacophore the request has failed at what it was for, and that is
the flag. An `intent_not_achieved` conflict at `major` downgrades the
verdict to `feasible_with_changes` even where the chemistry is
untouched. That is the one place the ladder is not purely about
feasibility.

When the molecular check was valid, `exact_mw`, `formula`, pH-dependent
descriptors, and a 3D-ensemble *summary* are part of the context this
call receives. 3D energy is not a pharmacological argument.

---

## Tie-break among chemistry survivors

If more than one candidate survived conflict detection and the 2D
gate, this is where **Select better candidate** happens, lexicographically:

1. 2D-valid graphs only (hard gate).
2. `check_intent` outcome: intent met, then degraded/unknown, then
   `intent_not_achieved`.
3. 3D quality as a tie-break only: embedding success, convergence,
   fewer clashes. Never MMFF/UFF energy across different molecules.
4. A genuine remaining tie is recorded in `unknowns`. The report still
   names one `selected_id` by stable node-id order so later stages have
   a leaf to judge; that is bookkeeping, not a chemistry preference.

The chemistry tree is not rewritten. The loser is recorded, not
deleted (axiom 3). If no candidate passes 2D, `selected_id` is null.

---

## Citation target

`Target_Peptide_Master` is a valid citation target for the final
`audit_ref` gate, even though only this section queries it for
context. `score.py --audit` is handed **both** workbooks.

The sequence column in that workbook is a display column and is not
machine-parseable. Positions quoted inside it may use literature
numbering rather than position-in-string.

prev: [Molecular validation](05-molecular-validation.md) · [Index](../plan.md) · next: [Final judge](07-final-judge.md)
