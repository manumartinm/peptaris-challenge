# 05 — Molecular validation

**Purpose:** Reconstruct each surviving candidate as an RDKit molecule,
sanitize the 2D graph, compute formula / exact mass / physchem / pH
descriptors, and optionally request a Boltz 3D prediction. This is not
docking or MD, and the optional 3D result is supporting evidence rather
than proof of a bioactive conformation.

**Read this when:** you need what the molecular check produces, why a
graph bug is not a chemistry conflict, or how 3D quality may later
break an intent tie.

**Prerequisites:** [Conflict detection](04-conflict-detection.md)
survivors (`ConflictTree.surviving_ids`). `resolved_sequence`,
`resolved_annotations`, and `permanent_connectivity` are already
fixed on each surviving leaf.

[Index](../plan.md)

---

## What this process is

A deterministic check, run **once per surviving candidate** after the
conflict tree is walked, never per pruned branch. Checking a branch
that already failed compatibility is wasted work.

The molecule is assembled from a versioned fragment catalog
(`data/molecular_fragments.json`): backbone residues, termini, ncAA,
and conjugate fragments joined according to `permanent_connectivity`.
Protecting groups that do not survive to the product are not in the
graph. RDKit 2D sanitization and descriptors consume the canonical
`Mol`; optional Boltz 3D consumes the resolved peptide sequence.

If the 2D graph sanitizes, the candidate is eligible for intent. The
check records `formula`, `exact_mw`, TPSA, diagnostic cLogP, HBD/HBA,
formal charge, rotatable bonds, rings, heavy atoms, plus net charge
and an estimated pI at a configurable pH (default 7.4).

If it does not sanitize, or a required fragment is missing, that is a
**bug in the connectivity table / catalog**, not a finding about the
request's chemistry. No `conflicts[]` kind represents "the agent's own
graph is malformed." It is logged as a molecular issue, `unknowns`
says so plainly, and the candidate cannot win.

## Optional Boltz 3D

Each 2D-valid candidate may be sent to the Boltz structure-and-binding
API (`boltz-2.1`). The adapter submits one sequence, polls the prediction,
downloads the returned CIF, and records structure confidence, pTM, complex
pLDDT, and whether the configured confidence threshold was met.

Boltz currently receives the resolved backbone sequence and cyclic flag.
Conjugate fragments, N-methyl sites, non-standard residue overrides, and
other recipe unknowns are not encoded in that request. When those features
exist, the trace records `boltz_sequence_only` so the backbone prediction is
not mistaken for the complete designed product.

The 3D block is skipped when `BOLTZ_API_KEY` is absent, `--no-model` is
active, or `ROUTE_AGENT_MOLECULAR_SKIP_3D=true`. API failures and timeouts
produce molecular issues and unknowns; they do not invent a chemistry
conflict or discard the valid RDKit 2D evidence.

These metrics live on the internal post-graph report / trace. They are
not extra top-level CLI fields: [`schema.json`](../../data/schema.json)
forbids that.

## Rejected: SELFIES as the builder

SELFIES was considered for representing the final molecule instead of
building the graph from fragments. Rejected: this system constructs
exactly one molecule from a recipe already fixed by the surviving
leaf. A 2D validity-under-mutation guarantee buys nothing here, and
SELFIES still carries no conformational information. Mapped-SMILES
fragments plus RDKit already give sanitization and exact mass, while
the resolved sequence provides the optional Boltz input. SELFIES is
not the canonical product representation.

prev: [Conflict detection](04-conflict-detection.md) · [Index](../plan.md) · next: [Intent](06-intent.md)
