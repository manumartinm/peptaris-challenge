# 12 — Operational rules

**Purpose:** How `verdict` fires, how `conflicts[]` is filled, and
how a fix is attempted. The Agent does not know these rules as output
rights — it only produces findings.

**Read this when:** a case has the right chemistry and the wrong
verdict, or you need why three attempts became one conflict.

**Prerequisites:** [Conflict detection](04-conflict-detection.md)
tree. [Two outputs](09-outputs.md) field table. [Axioms](01-axioms.md)
1–3.

[Index](../plan.md)

---

## When `feasible_with_changes` fires

Walk the winning leaf's `parents` chain.

- If every family's first-tried candidate survived → `feasible`.
- If at least one family needed a sibling to survive →
  `feasible_with_changes`.
- If no leaf survives anywhere in the tree → see backward
  propagation in [Conflict detection § 3.5](04-conflict-detection.md)
  before declaring `infeasible` or `insufficient_information`.

`insufficient_information` dominates the other three. Verdict is the
worst over modifications, ordering
`feasible < feasible_with_changes < infeasible`.

A modification is `feasible_with_changes` iff you can name a concrete
alternative that still achieves the requested modification **at the
requested site**. Moving it to a different residue, or dropping it,
is a different request, not a change. A coordinate change is not a
relocation: if the requested residue still exists in the target and
only its index moved because the sequence changed, re-indexing it is
a valid resolution and the remap belongs in `site_map[].note`.

Choosing a resin or a protecting group **in the first place** is
designing the route, not changing it. A conflict is something the
request forces you to work around, not a decision you were always
going to make.

`intent_not_achieved` at `major` downgrades to
`feasible_with_changes` even when chemistry is untouched.

---

## How `conflicts[]` fills

Every failed candidate is recorded in the **trace**, never in the
output. `conflicts[]` is built once, from the winning path: one
consolidated entry per branch point that needed more than the first
attempt, `resolution` naming whichever candidate finally survived.

Three attempts (Mtt, ivDde, Alloc) produce **one** entry, not three.

Severity:

- `blocking` = no route exists at any cost
- `major` = the route as requested does not work and something must
  change
- `minor` = advisory (including a hazard you designed around)

A `major` or `blocking` finding next to `verdict: feasible` is a
contradiction. More than two kinds beyond what a key demands is
`+indiscriminate`.

An `order_of_operations` conflict is reported whenever two requested
modifications would destroy each other under the naive stage order,
even if `route` sequences them correctly.

---

## How a conflict gets a fix attempted

Not a separate call. The same `check_compatibility` invocation that
detects the failure reads the family's own `explicit_alternatives`
and proposes the next candidate in the same turn. This is why no
separate bounded critic-and-proposer loop is needed — pruning plus
sibling generation does that job structurally.

---

## How a fix can affect something earlier

**Local, the common case:** the surviving sibling changes nothing
decided before this branch point.

**Backward, rare:** walk `parents` for an unexplored ancestor
alternative before declaring final failure
([Conflict detection § 3.5](04-conflict-detection.md)).

prev: [Literature sandbox](11-literature-sandbox.md) · [Index](../plan.md) · next: [Spec corrections](13-spec-corrections.md)
