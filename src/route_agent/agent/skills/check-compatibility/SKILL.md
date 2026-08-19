---
name: check-compatibility
description: Evaluate whether a candidate modification process is chemically compatible with the current peptide state and propose valid same-site alternatives if conflicts arise.
---

# check_compatibility Skill

## 1. Objective

Evaluate whether applying a candidate modification process (`family`, `site`, `process`) to the current synthesis state (`protected`, `free_amines`, `catalysts_used`, `termini`, `permanent_connectivity`) causes chemical side-reactions, reagent incompatibilities, or loss of protecting group orthogonality. If a conflict occurs, propose an alternative process strictly from the family's explicit alternatives that achieves the **exact same modification at the exact same site**.

## 2. Input Context

- **State / prior work** (already decided before this check):
  - `prior.resin` / `state.route_step`: resin chosen in validation (e.g. Rink
    amide vs Wang vs 2-CTC). C-terminal amidation is that resin choice, not a
    later conversion of a cleaved acid.
  - `prior.sequence_snapshot`: resolved backbone currently on the tree.
  - `prior.parent_c_terminus`: **parent** peptide terminus. A free-acid parent
    plus a `c_term_amidation` candidate is the standard analog, not a clash.
  - `prior.history`: processes already accepted on this branch.
  - Ledgers: `protected`, `free_amines`, `catalysts_used`, `termini`.
- **`parent_target`**: row from the targets workbook for `parent_name`
  (`receptor_target`, `receptor_class`, `ligand_role`). Do not invent SAR.
  If `available` is false, leave pharmacology in `unknowns`.
- **`process_profile`** (the `process_id` row from extracted_families.json):
  - `summary`, `conditions`, `constraints`, `reagents`, `requires`,
    `explicit_risks`, `explicit_alternatives`, `building_blocks`.
  - Read **conditions first**. Risks about post-cleavage or low-yield
    alternatives describe what **not** to do; they do not fail the default
    process when conditions say the route is resin selection / zero extra steps.
- **Candidate**: `family`, `site`, `process`.

## 3. Systematic Chemistry Compatibility Checklist

Evaluate each of the following chemical interaction axes:

1. **Protecting Group Orthogonality**:
   - Will the deprotection reagent required by the candidate process prematurely cleave other protecting groups in `protected`?
     - *Mild acid (1-2% TFA / DCM)*: Cleaves `Mtt`, `Trt`, `Mmt`, `2-Cl-Trt`, `O-2-PhiPr`. Does NOT cleave `Boc`, `tBu`, `Pbf`.
     - *Hydrazine (2-3% in DMF)*: Cleaves `ivDde`, `Dde`. Safe for `Fmoc` (under controlled conditions), `Boc`, `tBu`, `Alloc`.
     - *Palladium catalyst / Scavenger (Pd(PPh3)4 + PhSiH3 or morpholine)*: Cleaves `Alloc`, `OAll`. Orthogonal to all acid/base-labile groups.
     - *Base (20% piperidine / DMF)*: Cleaves `Fmoc`. Cannot be used if other on-resin groups require surviving Fmoc backbone protection.
2. **Reagent & Side-Chain Incompatibility**:
   - Do the incoming reagents or catalysts react destructively with unmasked nucleophiles or functional side-chains?
     - *Olefin Metathesis (Ruthenium catalysts)*: Unprotected **thiols** (`Cys`) poison Grubbs catalysts — fail the process. A **Met thioether** is a documented risk, not an automatic fail: the default on-resin RCM still runs; record residual-Ru QC (ICP-MS) or Met protection as a minor note when the profile already lists those conditions. Only fail Met-containing sequences when the profile gives no executable RCM conditions.
     - *Disulfide Oxidation*: Reagents like iodine ($I_2$) can oxidize or iodinate unprotected `Trp` and `Tyr` residues. For **regioselective multi-bridge** folding, if the ledger has no orthogonal Cys handle (`Acm` vs `Trt`) and the process requires one, that is `building_block_availability` (the directed-folding building blocks are not in the state), not a proof that disulfides are chemically impossible.
     - *Acylation / Alkylation*: Attacks any unmasked nucleophilic amine (`free_amines`) or unprotected side-chain.
3. **Catalyst & Cleavage Poisoning**:
   - Check `catalysts_used`. If metal catalysts were introduced, flag the downstream requirement for specialized QC (e.g., ICP-MS trace metal analysis).
4. **Order of Operations**:
   - Does executing this process now preclude a subsequent requested modification, or would subsequent global cleavage (95% TFA) destroy fragile conjugated moieties?

## 4. Finding Kinds Taxonomy

When a conflict is detected, categorize it using one of these standard finding kinds:

- `protecting_group_orthogonality`: Non-orthogonal deprotection or cross-cleavage.
- `reagent_incompatibility`: Reagent degrades, oxidizes, or reacts with unintended functional groups. Use this (or `order_of_operations`) for Pd vs Ru clashes, not a site-token error.
- `order_of_operations`: Hazardous sequence of reaction conditions where a later step ruins an earlier step (Alloc/Pd lactam vs Grubbs staple on the same path).
- `building_block_availability`: Required reagent / building block is unavailable or synthetically intractable.
- `mutually_exclusive`: Two **requested** modifications occupy or compromise the same site or mechanism. Parent `free_acid` vs analog C-terminal amide is **not** mutually exclusive. Head-to-tail cyclization vs C-terminal amide **is**.
- Do **not** emit `site_invalid`. That kind is reserved for the parser when a site token fails grammar or coordinate-frame checks.

## 5. Alternative Candidate Resolution Protocol

1. Read `process_profile` in the user payload (summary, conditions, risks, alternatives, reagents). Call `family_profile_lookup` only if you need another process_id.
2. If the current candidate fails, check the family's `explicit_alternatives` list. An "avoid" alternative is not a reason to fail the default process.
3. Propose a concrete alternative process (e.g., `"lipidation_via_alloc"`) that preserves the **same modification at the same site**.
4. If no alternative candidate exists in the corpus profile, set `resolution: null`.
5. **Hard Rule**: Never propose moving the modification to a different residue or omitting the modification.

## 6. Tools & Grounding Protocol

- Use `family_profile_lookup(family, process_id)` only if `process_profile` in the payload is missing a needed process_id.
- Use `audit_ref(kind, ref_or_source, basis)` to verify all corpus row citations (`ref_row`) or literature claims.
- If literature is necessary, call native `web_search` once (`filetype:pdf`). Do not call `task()`. Then `web_fetch` or `fetch_and_parse`, then `audit_ref`.

## 7. Output Contract

Produce structured `AgentResult`:

- `passed`: `true` if compatible, `false` if conflict detected, `null` if degraded / insufficient evidence.
- `findings`: List of `AgentFinding` objects with `kind`, `description`, and `affected` site tokens.
- `resolution`: Exact process string for the next alternative candidate, or `null`.
- `citations`: Grounded `Provenance` entries verified by `audit_ref`.
- `unknowns`: Explicitly state any unresolvable questions or uncertainties.
- **NEVER** output `verdict` or attempt to write the global route verdict.
