# 14 — Three-day order

**Purpose:** What happens on which day.

**Read this when:** you need the calendar, or what gets cut first.

**Prerequisites:** [System overview](00-overview.md). Cut order from
the challenge: §9 extensions, then no-corpus ablation, then cases
beyond six. The clean-clone check and the README are not cut.

[Index](../plan.md)

---

## Calendar

| When | What |
|---|---|
| Kickoff | Ask for the missing files. Resolve the multi-range `site_map` ambiguity here if possible |
| Day 1 AM | Read `score.py` in full. Read the corpus in full. Sketch the tree by hand for the two or three families you know will branch |
| Day 1 PM | Six self-authored cases exist before anything runs against them. Validation Engine and the route-skeleton seed exist |
| Day 2 | `extracted_families.json` is dense. The Agent's three objectives are live. `eval` runs end to end. Ablation B, on and off. Scramble control. `--agreement` on the dev set, pinned model and temperature |
| Day 2 night | `CORPUS_ERRATA.md` |
| Day 3 09:00 | Freeze. Forecasts with real spread, one line each. No code changes after this point |

Molecular validation and the literature sandbox belong on Day 2 if
the tree and Agent already run.

Day 1 PM covers [Base types](02-base-types.md) and
[Validation Engine](03-validation-engine.md), plus a route-skeleton
seed from [Conflict detection](04-conflict-detection.md). The six
self-authored cases include at least one plausible negative control
and at least two clean `feasible` cases.

Day 2 covers [family profiles](10-extracted-families.md), the rest of
conflict detection, [the Agent](08-agent.md), [intent](06-intent.md),
[final judge](07-final-judge.md), [outputs](09-outputs.md), and
[operational rules](12-operational-rules.md). Optional: ablation A
([spec corrections](13-spec-corrections.md)) and
[literature](11-literature-sandbox.md) if an `external` citation is
needed.

---

## Freeze

09:00 Day 3. Forecasts with real spread, one line each. No code
changes after this point.

prev: [Spec corrections](13-spec-corrections.md) · [Index](../plan.md)
