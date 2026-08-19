# 01 — Axioms

**Purpose:** Six rules that hold everywhere. Every later process explains
how a specific mechanism enforces one of these. None of them are
enforced by convention alone.

**Read this when:** two pages seem to disagree about what a component
is allowed to do.

**Prerequisites:** [System overview](00-overview.md).

[Index](../plan.md)

---

## The six rules

1. **No component writes `verdict` except the final assembly.** The
   severity ladder is computed from the winning candidate's
   accumulated findings, never phrased by an LLM. See
   [Operational rules](12-operational-rules.md) and
   [Two outputs](09-outputs.md).

2. **No component repairs the request to make it pass.** A resolution
   must achieve the same modification at the same site. Moving it or
   dropping it is a different request, not a fix. The Agent may propose
   a `resolution` only under that constraint
   ([The Agent](08-agent.md)).

3. **Every critique is monotonic in the pessimistic direction.** A branch
   can be pruned, a citation can be discarded, a finding can be escalated.
   Nothing removes a real finding to improve the outcome.

4. **Every state is immutable and carries a maximally verbose error
   list.** A node is never edited, only extended with a new child whose
   `parents` points back. Types live in [Base types](02-base-types.md).

5. **Every citation is verifiable against a real source.** Corpus with an
   exact row, or literature with a URL a tool actually returned and a
   passage a tool actually fetched. `audit_ref` is deterministic
   ([Final judge](07-final-judge.md),
   [Literature sandbox](11-literature-sandbox.md)).

6. **Free text never reaches judgment unstructured.** `parent_features`,
   `modifications[].detail`, and `intent` pass through a grounded
   structurer before anything reasons over them
   ([Validation Engine](03-validation-engine.md)).

prev: [Overview](00-overview.md) · [Index](../plan.md) · next: [Base types](02-base-types.md)
