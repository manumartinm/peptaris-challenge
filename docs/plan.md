# route-agent — domain process notes

This series records the detailed domain rules behind each pipeline process.
For the implemented system, start with:

- [Getting started](getting-started.md) for installation and operation;
- [Architecture](architecture.md) for package boundaries and runtime data flow;
- [Trace Explorer](trace-explorer.md) for the UI and jobs API;
- [System overview](plan/00-overview.md) for the chemistry-process model.

The source code and tests are authoritative when an older planning note differs
from current behavior. `plan/00-overview.md` is the canonical process summary;
later pages explain individual domain decisions.

**Current correction:** the matrix-based design in earlier drafts is obsolete. There is no
`conflict_matrix.json` and no `family_pair_cache.json` as separate
persisted files. See [Conflict detection](plan/04-conflict-detection.md)
and [Spec corrections](plan/13-spec-corrections.md).

| # | Process | What it is |
| ---: | --- | --- |
| [00](plan/00-overview.md) | System overview | The full system in one place |
| [01](plan/01-axioms.md) | Axioms | Six rules that hold everywhere |
| [02](plan/02-base-types.md) | Base types | The records every later process writes and reads |
| [03](plan/03-validation-engine.md) | Validation Engine | One deterministic pass. Produces `State_0` |
| [04](plan/04-conflict-detection.md) | Conflict detection | State tree, candidates, pruning, route assembly |
| [05](plan/05-molecular-validation.md) | Molecular validation | RDKit 2D gate, descriptors, 3D ensemble per survivor |
| [06](plan/06-intent.md) | Intent | Whether surviving chemistry meets the design goal |
| [07](plan/07-final-judge.md) | Final judge | Gaps, confidence, citation verification |
| [08](plan/08-agent.md) | The Agent | One agent, three objectives. Never writes `verdict` |
| [09](plan/09-outputs.md) | Two outputs | Schema-exact CLI JSON + internal trace |
| [10](plan/10-extracted-families.md) | Family profiles | The only offline corpus artifact |
| [11](plan/11-literature-sandbox.md) | Literature sandbox | Network tools + committed `/research/` cache |
| [12](plan/12-operational-rules.md) | Operational rules | Verdict ladder, how `conflicts[]` fills |
| [13](plan/13-spec-corrections.md) | Spec corrections | Ablation A wording now that the matrix is gone |
| [14](plan/14-three-day-order.md) | Delivery history | Original three-day implementation order; historical, not an operator guide |
