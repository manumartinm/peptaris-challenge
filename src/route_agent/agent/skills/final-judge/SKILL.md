---
name: final-judge
description: Review the complete trace of the winning synthetic candidate, audit all citations against corpus/cache, identify unresolved gaps, and evaluate confidence using a strict rubric.
---

# final_judge Skill

## 1. Objective

Perform a comprehensive audit of the winning candidate's entire execution trace. Identify unmapped gaps or unanchored assumptions across the route, verify every citation against the underlying corpus and persisted literature cache using `audit_ref`, and assign a calibrated `confidence` rating (`high`, `medium`, `low`) following a deterministic checklist.

## 2. Comprehensive Trace Audit Checklist

Inspect the accumulated trace of the winning leaf **and every modification on the request**:

1. **Requested vs applied modifications**:
   - Read `requested_modifications` (family, site, detail, index) and `family_bindings`.
   - Read `applied_modifications` on the winning path (process, site, family, status, findings).
   - Confirm every requested modification is represented by an applied process at the same site. A missing, dropped, or relocated modification is a gap.
   - Do not judge only the leaf `candidate`; orthogonality and order-of-operations span the full applied set.
2. **Grounded Structurer Spans**:
   - Verify if any free-text segment from `parent_features`, `modifications[].detail`, or `intent` remained in `unmapped_spans`.
3. **Intermediate Node Health**:
   - Check if any intermediate state node on the winning path was marked as `degraded` (e.g., partial information or timeout fallback).
4. **Trace-Level Quality Control (QC) Consistency**:
   - Check `catalysts_used`. If transition metal catalysts (e.g. Ruthenium Grubbs/Hoveyda catalysts, Copper click catalysts, Palladium deprotection reagents) were employed, verify that trace metal analysis (ICP-MS) is accounted for in the QC stage.
5. **Synthetic Step Continuity**:
   - Confirm that the reconstructed route forms a continuous, feasible synthetic trajectory from resin selection through chain assembly, on-resin modification, cleavage/deprotection, purification, and QC.

## 3. Strict Deterministic Confidence Rubric

Evaluate and assign `confidence` using this non-negotiable rubric:

- **`high`**:
  - 100% of all citations have `kind: "corpus"` with verified workbook rows.
  - Exactly **0** degraded nodes in the winning path.
  - Exactly **0** unmapped structurer spans.
  - Exactly **0** external literature consultations (`search_literature` / `web_search`).
- **`medium`**:
  - Any valid citation has `kind: "inference"` or `kind: "external"` (literature verified in `/cache/`).
  - Or non-fatal degradation / minor ambiguity in reaction parameters that does not compromise overall route viability.
- **`low`**:
  - Route outcome is `insufficient_information` or `infeasible`.
  - Any unresolved gap, missing building block, or unanchored assumption touching an emitted conflict.

## 4. Hard Citation Audit Gate (Axiom 5)

Every citation claiming `corpus` or `external` provenance must be audited with `audit_ref`:

1. Call `audit_ref(kind="corpus", ref_or_source=..., basis=...)` for corpus rows.
2. Call `audit_ref(kind="external", ref_or_source=..., basis=...)` for literature markdown in `/cache/`.
3. **Hard Rule**: If `audit_ref` fails to confirm the citation or basis terms, the citation is stripped / degraded and MUST NOT be emitted in `citations`.
4. Stubs or paywall hits marked as `thin_content` (<500 characters) in `/cache/` cannot serve as verified citations; move the underlying claim to `unknowns`.

## 5. Output Contract

Produce structured `AgentResult`:

- `confidence`: Exactly `"high"`, `"medium"`, or `"low"`.
- `gaps`: Tuple of identified trace or structural gaps (or empty `()`).
- `unknowns`: Tuple of remaining uncertainties.
- `citations`: Tuple of `Provenance` entries that strictly passed `audit_ref`.
- **NEVER** write `verdict` (the final verdict is computed deterministically in pure code by applying the severity ladder to accumulated findings).
