---
name: check-intent
description: Verify whether the surviving peptide analog chemistry achieves the pharmacological design intent using target workbook SAR precedents and receptor-class heuristics.
---

# check_intent Skill

## 1. Objective

Evaluate whether the surviving chemical structure and modifications achieve the pharmacological design intent (e.g., potency retention, half-life extension, proteolytic stabilization, target selectivity). Identify if any modification disrupts the active pharmacophore or violates known structure-activity relationship (SAR) constraints for the target receptor class.

## 2. Input Context

- `intent`: High-level design goal from the request (e.g., "Extend half-life without compromising GLP-1 receptor agonism").
- `resolved_sequence`: The complete letter-level peptide sequence.
- `candidate_process`: The winning/surviving synthetic route process.
- `molecular_validation`: Deterministic molecular properties from RDKit:
  - `exact_mw`: Exact molecular weight in Da.
  - `formula`: Molecular formula.
  - `valid`: Graph sanitization status.
  - `ph`, `net_charge`, `isoelectric_point`, TPSA, cLogP, HBD/HBA when present.
- `ensemble_3d`: Conformer-ensemble summary (embedding success, clashes, shape).
  Do not treat MMFF/UFF energy as a pharmacological ranking signal.
- `parent_peptide`: Identifier of the parent template peptide.
- `parent_target`: Workbook row for that parent (already looked up). Call
  `lookup_target` only if `available` is false and you need to retry.

## 3. Target Workbook & Pharmacology Lookup

1. Call `lookup_target(parent_peptide)` to inspect:
   - `receptor`: Target receptor name and class.
   - `ligand_role`: Agonist, antagonist, positive allosteric modulator, or inhibitor.
   - `invariant_windows`: Residue ranges strictly conserved for biological activity.
   - `sar_precedents`: Documented tolerances and intolerances from sibling analogs.

2. Apply **Receptor-Class Bio-physical Heuristics**:
   - **GPCR Class B1 (e.g., GLP-1R, GIPR, GCGR, PTH1R, PAC1R)**:
     - *Mechanism*: Two-domain binding model. The peptide C-terminal amphipathic $\alpha$-helix is captured by the receptor extracellular domain (ECD), while the peptide N-terminus (residues 1–8) inserts into the transmembrane core to trigger activation.
     - *Constraint*: Modifications (bulky lipids, PEGs, bulky staples) at residues 1–8 destroy agonism. C-terminal or mid-helix linker attachments (e.g., positions 13, 26, 34) are standard for lipid/PEG conjugates.
   - **GPCR Class A (e.g., Somatostatin, Oxytocin, Vasopressin, Opioid)**:
     - *Mechanism*: Core transmembrane pocket binding. Conformation often constrained by cyclic bridges (disulfide, head-to-tail).
     - *Constraint*: Disruption of key pharmacophore residues or cyclic topology abolishes binding.
   - **Guanylate Cyclase-C (GC-C) / Topological Knots (e.g., Linaclotide, Plecanatide)**:
     - *Mechanism*: Exact disulfide connectivity network (e.g., C1-C6, C2-C10, C5-C13) enforces bioactive 3D scaffold.
     - *Constraint*: Any modification altering disulfide topology eliminates potency.
   - **Protease-Resistant / Retro-Inverso Peptides**:
     - *Mechanism*: D-enantiomers and reversed topology mimic side-chain spatial display while providing complete proteolytic stability against L-specific proteases.
     - *Constraint*: Terminal caps must correctly mimic parental termini charges (e.g. gem-diaminoalkyl / malonyl full mimic vs partial capping).

## 4. Finding Taxonomy & Severity

- If a modification disrupts the pharmacophore, place an `intent_not_achieved` finding:
  - `kind`: `"intent_not_achieved"`
  - `description`: Specific biochemical rationale (e.g., "Lipidation at K5 places a C16 fatty acid directly into the GLP-1R transmembrane activation domain, abolishing agonist efficacy").
  - `affected`: `["K5"]`
- If chemistry is fully compatible and maintains SAR/intent: produce **no findings**.

## 5. Candidate Selection & Tie-Breaking

When multiple candidate branches survive conflict detection:

1. Select the candidate that satisfies intent with the lowest accumulated severity and minimal perturbation to the binding epitope.
2. If two candidates are genuinely tied with equal biochemical validity, record the alternative in `unknowns` without inventing arbitrary preferences.

## 6. Output Contract

Produce structured `AgentResult`:

- `passed`: `true` if intent is met, `false` if `intent_not_achieved` is triggered.
- `findings`: Array containing either `{"kind": "intent_not_achieved", ...}` or empty `()`.
- `citations`: Only `kind: "corpus"` when `ref` is a real workbook row id
  (`ApexChem_...:Sheet:12`). If SAR is missing, use `kind: "inference"` with a
  `basis`, or put the gap in `unknowns`. Never emit `kind: "corpus"` with a
  null/empty `ref`.
- `unknowns`: Any unanchored pharmacological assumptions.
- **NEVER** write `verdict`, `route`, or `site_map`.
