# 04 — Conflict detection: the state tree

**Purpose:** Build candidates, ask `check_compatibility` on each, prune
failures, and assemble `route` once from the winning leaf.

**Read this when:** you need how candidates branch, why a sibling
died, or how `route` is assembled.

**Prerequisites:** [Validation Engine](03-validation-engine.md)
(`State_0`). [Family profiles](10-extracted-families.md) for
`stage_hint` and `explicit_alternatives`. [The Agent](08-agent.md) for
the call shape.

**Supersedes:** a persisted `conflict_matrix.json` /
`family_pair_cache.json`. Compatibility is a live, cached Agent call
against `extracted_families.json`.

[Index](../plan.md)

---

## 3.1 Route skeleton

Using each active family's `stage_hint` (a field in
`extracted_families.json`, not a separate matrix), plus `route_seed`
and the resin already chosen, build the seven-stage skeleton. Still no
LLM. Bulk chain assembly for residues that no family branches on is a
**single seed step**, not one node per residue.

Stages on the emitted `route`:
`resin_selection · chain_assembly · on_resin_modification ·
n_terminal_cap · cleavage · solution_phase · purification · qc`.

---

## 3.2 Candidate generation (P1..PN)

Most modifications have exactly one way to be done — one candidate, a
simple chain. Some have several:

- **Protecting-group choice.** Lipidation's target lysine can go
  through Mtt, ivDde, or Alloc. Each is a sibling candidate.
- **Retro-inverso's termini treatment.** Partial (normal caps on the
  new termini) versus full mimic (gem-diaminoalkyl at the new N-term,
  malonyl at the new C-term). The backbone letters are identical
  either way; `resolved_sequence` never changes between them. What
  differs is what occupies the termini, which is state, not sequence.
- **`special_residues`, `spps_foundation`, most other families.** No
  second way exists. One candidate, no branch.

---

## 3.3 Check compatibility

Before each Agent invocation the walker rebuilds `protected` from scratch:
residue defaults, then every operation already in `prior.history`, then the
candidate process. Future modifications are not marked pending yet. That map
is the state `check_compatibility` sees, and it can fail the node on its own
if the census has a deterministic error.

One Agent invocation per remaining candidate, objective `check_compatibility`:

```
Prior: {resin, sequence_snapshot, parent_c_terminus, history}
State: {protected: {...}, free_amines: {...}, catalysts_used: {...},
        termini: {...}}
Candidate: family=lipidation, site=K13, process=Alloc

Does this process, applied to this state, attack anything that is not
its own intended target? Use family_profile_lookup against
extracted_families.json to verify. If it conflicts, does the family's own
explicit_alternatives list a different process that achieves the same
modification at the same site? Propose it as the next candidate to try.
```

Detecting a failure and proposing the fix are the **same call**, not
two. There is no separate critic-and-proposer loop; a bad candidate is
not argued with, it is pruned, and a surviving sibling takes its
place. If no sibling survives and the family's own profile lists no
further alternative, the honest answer is that no resolution exists,
reported as `resolution: null`.

**Tools** (same list on every Agent call): see
[The Agent](08-agent.md).

**Caching.** Keyed on
`(candidate_process, candidate_site, frozenset(state_categories_present))`.
Site stays in the key so findings bound to one residue are never replayed at
another. Categories abstract chemically relevant ledger facts — protecting-group
families such as `Fmoc_must_survive` and `mild_acid_labile_side_chains_present`,
free amines, catalysts, topology class, and history processes — never
`request_id`. The chemistry fact is the same regardless of which request
reached that `(process, site, categories)` triple.

---

## 3.4 Pruning and selection

A failed candidate produces `route_step=None` and no children. A
surviving candidate continues. If several survive equally, the tie is
resolved in [Intent](06-intent.md), and the one not chosen is recorded
in `unknowns`, not discarded silently.

---

## 3.5 Backward effects, when all siblings die

Two cases, very different in cost:

**Local fix (the common case).** A surviving sibling exists at the same
branch point. Continue forward. Most conflicts in this corpus resolve
here.

**Backward propagation (rare).** All siblings at a point die. Before
declaring the whole route infeasible, walk up `parents` looking for
the nearest ancestor that had an unexplored alternative of its own —
resin choice being the most likely candidate if the corpus genuinely
offered more than one option for that `parent_c_terminus`. If found,
re-root a new subtree there with the new constraint attached, and
prune the old subtree. If no such ancestor exists, the failure is
real: `infeasible` or `insufficient_information`, with the causal
chain spelled out in `unknowns`.

---

## 3.6 Route reconstruction

`route` is never appended to during the walk. It is assembled once, by
walking `parents` backward from the winning leaf to the root,
collecting every node whose `route_step` is not `None`, then reversing
that list. The deterministic tail is then appended: cleavage,
purification, and QC (ICP-MS only if `catalysts_used`).

No step is pre-classified as belonging to a fixed tier. A stage that
is independent of the tree in one request (n-terminal capping in most
cases) can become tree-dependent in another (n-terminal capping, if
retro-inverso's full-mimic branch put a non-standard building block at
that terminus instead of a normal amine, per `05_N_Term_Acetylation`'s
own profile possibly not applying at all).

One emitted step per operation. A stage repeats when it contains two
ordered operations. An `order_of_operations` conflict is reported
whenever two requested modifications would destroy each other under
the naive stage order, **even if `route` sequences them correctly**.
The conflict records the hazard; the `route` records the handling.

---

## 3.7 Two ledgers, never merged

`output["protected"]` holds short labels for cheap comparison during
`check_compatibility`. `output["permanent_connectivity"]`, a growing
tuple of `Bond`, holds only bonds that survive to the final product,
appended by whichever node commits them, never by a node that only
swaps a temporary cap.

`building_block` (the exact `Fmoc-...-OH` string) is populated on
every attempt, pass or fail, sourced verbatim from
`extracted_families.json`, never reconstructed from the short label.
`sequence_snapshot` renders the whole chain, position by position,
from `resolved_sequence` plus whatever
`protected` / `free_amines` / `permanent_connectivity` say at that
exact node, purely for human readability, never parsed back by any
check.

prev: [Validation Engine](03-validation-engine.md) · [Index](../plan.md) · next: [Molecular validation](05-molecular-validation.md)
