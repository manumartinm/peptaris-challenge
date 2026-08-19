# 03 — Validation Engine

**Purpose:** One deterministic pass over the request. No LLM for
chemistry. Produces `State_0`. Fixes letters and sites; does not decide
protecting-group branches or retro-inverso termini treatment.

**Read this when:** you need what `State_0` contains, or why a
`site_invalid` appeared here rather than later.

**Prerequisites:** [Base types](02-base-types.md). Axiom 6 (free text
is structured here).

[Index](../plan.md)

---

## What this process does

One pass, in order, producing `State_0`.

| Step | Does | Produces |
|---|---|---|
| `validate_sequence` | Alphabet check, 1-based indexing | `residues[]` |
| `validate_modification_sites` | Comma-separated list of atoms (single position or range) plus four keywords (`N-term`, `C-term`, `both termini`, `whole sequence`). Handles N atoms of either kind, including a multi-range list like a triple interleaved disulfide | `sites_resolved[]`, or `site_invalid` |
| `parent_features` | Grounded structurer (axiom 6): classifies each free-text feature, extracts an embedded site token if present | `occupancy`, `route_seed` |
| `resolve_family` | Maps each `family` string to its profile in `extracted_families.json` | family bindings |
| `resolve_sequence` | Applies the *letter-level* transform only, retro-inverso's reversal plus D-conversion, or a direct substitution. Never branches: there is exactly one correct letter per position, always | `resolved_sequence`, `resolved_annotations`, `index_map` |
| `sacar_grupos_protectores` | Census of which protecting group each residue type requires | seeds `State_0.output["protected"]` |
| `seleccionar_resina` | Three-input decision tree: `parent_c_terminus`, amidation requested, cyclization anchor requested | seeds `State_0.route_step` |

The model is **not** used for index arithmetic, site validity, or
enums. A grounded structurer may run on `parent_features`,
`modifications[].detail`, and `intent` so that free text never reaches
later judgment unstructured. That is classification, not chemistry.

`ApexChem_templates_and_targets.xlsx` does not enter here. That
workbook enters only in [Intent](06-intent.md).

---

## Two structural facts

`site_invalid` is the **only** conflict kind this stage can produce. An
error fallback anywhere else that maps "I don't understand this" to
`site_invalid` is a bug, not a finding.

`resolve_sequence` fixes the *letter*, never the extra structure a
family might add at a fixed position. Retro-inverso's full-mimic
termini are a later decision
([Conflict detection § 3.2](04-conflict-detection.md)), because
whether to add them depends on context that is not known yet.

`State_0.output["protected"]["K13"]` (or whichever position a branching
family targets) starts as `"pending"`, not a real value, because
assigning it is exactly the question the next process answers.

Choosing a resin is designing the route, not a conflict.

---

## Site grammar

`K12` · `V21,R25` · `C2-C7` · `C1-C6, C2-C10, C5-C13` · `N-term` ·
`C-term` · `both termini` · `whole sequence`. Whitespace around
separators is insignificant.

`site_map` is produced here, over `modifications` only — never over
`parent_features`. A multi-position token expands to one entry per
position, each echoing the **whole** requested token. `both termini`
expands to `N-term` and `C-term`. `whole sequence` gets one entry
echoing the token. For keyword sites, `residue` is `null`.

`resolved_sequence` is the target backbone: one letter per backbone
residue. Side-chain conjugates are not represented. A stereochemistry
change alone does not change the letter. Whole-sequence inversion is
the reversed string.

prev: [Base types](02-base-types.md) · [Index](../plan.md) · next: [Conflict detection](04-conflict-detection.md)
