# 00 — System overview

**Purpose:** The domain-process model behind the implemented route-agent
pipeline. Every other page in this series covers one part in depth. For package
boundaries, persistence, API behavior, and current runtime trade-offs, use the
[architecture guide](../architecture.md).

**Read this when:** onboarding, resolving a conflict between two other
pages, or explaining the architecture.

**Supersedes:** the matrix-based design in earlier drafts of conflict
detection. There is no `conflict_matrix.json` and no
`family_pair_cache.json` as separate persisted files.
[Spec corrections](13-spec-corrections.md) point 7 is corrected there.

**Interfaces:** the public operator guide is [`README.md`](../../README.md),
with detailed [setup](../getting-started.md) and
[Trace Explorer](../trace-explorer.md) guides.
`route-agent --help` lists `run`, `validate`, `config`, `doctor`, and `debug`.

**Prerequisites:** none. Everything else builds on this.

[Index](../plan.md)

---

## What the tool does

`route-agent` takes a design request (parent peptide + requested
modifications + intent) and returns a route verdict: can this analog be
made, in what order, with which protecting-group scheme, and where will
it break.

The system is a **deterministic pipeline with a model used only where
judgment is needed**. Sequence parsing, site arithmetic, resin choice,
route assembly, the severity ladder, and citation verification are
deterministic. The Agent has three bounded objectives —
`check_compatibility`, `check_intent`, and `final_judge`. A separate bounded
structurer can normalize genuinely free-form parent features during
validation. In `--no-model` mode these judgments become explicit unknowns.

```text
request
  → Validation Engine (no LLM) → State_0
  → route skeleton + candidate tree (no LLM to build)
  → check_compatibility per candidate (Agent)
  → prune / backward-propagate
  → RDKit 2D check per surviving leaf + optional Boltz 3D
  → check_intent per 2D-valid survivor (Agent)
  → final_judge once (Agent) + audit_ref (deterministic)
  → assemble CLI output + trace
```

---

## Axioms (enforced, not conventional)

Full text: [Axioms](01-axioms.md).

1. No component writes `verdict` except the final assembly.
2. No component repairs the request to make it pass.
3. Every critique is monotonic in the pessimistic direction.
4. Every state is immutable and carries a maximally verbose error list.
5. Every citation is verifiable against a real source.
6. Free text never reaches judgment unstructured.

---

## Process map

| Process | Produces | LLM? |
| --- | --- | --- |
| [Base types](02-base-types.md) | `Error`, `Provenance`, `State`, … | No |
| [Validation Engine](03-validation-engine.md) | `State_0`, `resolved_sequence`, `site_map` | Structurer only, on free text |
| [Conflict detection](04-conflict-detection.md) | State tree, winning leaf, `route` | `check_compatibility` per candidate |
| [Molecular validation](05-molecular-validation.md) | formula, exact MW, descriptors, optional Boltz 3D, or a logged graph bug | No LLM; optional external 3D API |
| [Intent](06-intent.md) | `intent_not_achieved` or nothing; tie-break | `check_intent` per survivor |
| [Final judge](07-final-judge.md) | gaps, `confidence`; citations degraded if unverifiable | `final_judge` once |
| [The Agent](08-agent.md) | pass/fail, alternatives, gaps — never `verdict` | Yes |
| [Two outputs](09-outputs.md) | schema-exact JSON + `traces/{id}.trace.json` | No |
| [Family profiles](10-extracted-families.md) | `extracted_families.json` | Offline, once per tab |
| [Literature sandbox](11-literature-sandbox.md) | committed `/research/` cache | Tools only |
| [Operational rules](12-operational-rules.md) | `verdict`, consolidated `conflicts[]` | No |

---

## Two facts that used to be easy to get wrong

**No pre-computed conflict matrix.** `check_compatibility` reads
`extracted_families.json` live, through `family_profile_lookup`, cached
by `(candidate_process, frozenset(state_categories_present))`. That is
the one deliberate simplification from earlier drafts.

**`route` is assembled once, backward**, from the winning leaf to the
root, then the deterministic tail (cleavage, purification, QC) is
appended. Nothing appends to `route` during the walk.

---

## Delivery history

The [three-day order](14-three-day-order.md) records the original delivery
sequence. It is historical context, not a current operating or release plan.

[Index](../plan.md) · next: [Axioms](01-axioms.md)
