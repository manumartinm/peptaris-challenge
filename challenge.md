# ApexChem — 3-Day Technical Challenge

**Project:** `route-agent` — a synthesizability checker for designed peptide analogs
**Location:** Philadelphia, on-site · **Duration:** 3 working days
**Compute:** your laptop · **Data:** no laboratory data, no proprietary partner material

---

## 1. Context

Peptaris designs peptide therapeutics. ApexChem is the platform arm: AI-enabled structural
modification of peptide templates to improve developability — take a peptide that already engages its
receptor and modify it so it survives proteases longer, absorbs better, or gains selectivity.

The design side produces peptide sequences. Something then has to answer a separate question:

> **Can this peptide actually be made, in what order, with which protecting-group scheme, and where
> will it break?**

Today a chemist answers that by reading a spreadsheet. A campaign generates hundreds to low thousands
of analogs across 14 modification families and their hybrids. The failure that costs most is a
plausible-looking route that is chemically impossible — usually because two modifications have
incompatible deprotection chemistry, or because the request is self-contradictory.

---

## 2. What to build

A command-line tool, `route-agent`, that takes a **design request** and returns a **route verdict**.

### Input

A real request from the dev set:

```json
{
  "request_id": "REQ-05",
  "parent_name": "octreotide",
  "sequence": "FCFWKTCX",
  "parent_c_terminus": "alcohol",
  "residue_annotations": {"F1": "D-Phe", "W4": "D-Trp", "X8": "threoninol (Thr-ol)"},
  "parent_features": ["disulfide C2-C7"],
  "modifications": [
    {"family": "pegylation", "site": "K5", "detail": "discrete Fmoc-PEG4, on-resin"}
  ],
  "intent": "improve solubility without disturbing the bridge"
}
```

**Reading the input:**

- `sequence` is one-letter, 1-indexed, L-amino acids unless annotated. `X` marks a residue with no
  standard one-letter code. Every `X` is declared in `residue_annotations`; D-residues and other
  variants sharing a parent side chain keep the parent letter and are declared there too.
- `parent_c_terminus` describes the **parent**. A requested change appears in `modifications`. Noticing
  when the two cannot both hold is your job.
- `parent_features` are chemical features **or synthesis context** the parent already carries — a
  disulfide, an existing lactam, the resin it was assembled on. **Free text that may embed a site
  token — parse what you can, do not reject.** They are not requests, but they constrain the route.
- `modifications[].detail` is optional and may be absent.
- `site` grammar: `K12` · `V21,R25` · `C2-C7` · `C1-C6, C2-C10, C5-C13` · `N-term` · `C-term` · `both termini` (a modification
  anchored at both, e.g. head-to-tail closure) · `whole sequence`. Whitespace around separators is insignificant.
- `family` is one of: `spps_foundation`, `special_residues`, `n_methylation`, `c_term_amidation`,
  `n_term_acetylation`, `lipidation`, `pegylation`, `glycosylation`, `cyclization`,
  `hydrocarbon_stapling`, `disulfide`, `biaryl_bisalkylation`, `aza_peptide`, `retro_inverso`,
  `charge_hybrids`. These map onto the corpus tabs `01_`…`15_` in that order.

### Output

`schema.json` in this package is authoritative; the shape is:

```json
{
  "request_id": "REQ-05",
  "verdict": "feasible | feasible_with_changes | infeasible | insufficient_information",
  "confidence": "high | medium | low",
  "resolved_sequence": "target backbone, one letter per backbone residue",
  "resolved_annotations": {"X27": "Nle"},
  "site_map": [
    {"requested": "K5", "resolved": "K5", "residue": "Lys", "note": null}
  ],
  "route": [
    {"step": 1, "stage": "resin_selection", "operation": "...",
     "provenance": [{"kind": "corpus", "ref": "..."}]}
  ],
  "conflicts": [
    {"severity": "blocking | major | minor",
     "kind": "protecting_group_orthogonality | order_of_operations | mutually_exclusive | site_invalid | reagent_incompatibility | building_block_availability | intent_not_achieved",
     "description": "...", "affected": ["K5"],
     "resolution": "concrete alternative, or null if none exists",
     "provenance": [{"kind": "corpus", "ref": "..."}]}
  ],
  "unknowns": ["what you could not determine, and why"]
}
```

**Provenance.** Every claim carries one of three forms:

```json
"provenance": [
  {"kind": "corpus", "ref": "ApexChem_Synthesis_Reactions_by_AminoAcid:06_Lipidation:24"},
  {"kind": "inference", "basis": "one sentence of mechanism",
   "refs": ["ApexChem_Synthesis_Reactions_by_AminoAcid:09_Cyclization:23"]},
  {"kind": "external", "source": "DOI, URL or citation", "basis": "what it supports"}
]
```

`provenance` is an **array** — a claim that joins two sheets should cite both, and an `inference`
may carry `refs` to rows that support a premise without stating the conclusion.

`ref` is `workbook_filename_stem:sheet_name:row`, 1-indexed as openpyxl reports it. We check citations with `score.py --audit`, which takes **both** workbooks —
`score.py --audit <your_output>.jsonl ApexChem_Synthesis_Reactions_by_AminoAcid.xlsx ApexChem_templates_and_targets.xlsx`; hand it one and every ref to the other
is reported as `wrong_workbook_refs`. A `ref` must name one of the two supplied workbooks, an
existing sheet, and a real content row. **It checks reachability, not support** — a human reads whether
the row actually backs the claim, and that is where a fabricated citation is caught. `inference[].refs` are checked the same way, and a claim with no provenance at all is
counted. **Some of the most important things you will need to say are not in the corpus at all** — the corpus describes each
modification family in isolation and says almost nothing about how two of them interact. Asserting a
mechanism you can argue for, labelled `inference`, is expected and is not penalised. Fabricating a
corpus `ref` that does not support the claim is the one unrecoverable error here.

**Definitions we grade against, so you do not have to guess:**

- `severity`: `blocking` = no route exists at any cost · `major` = the route as requested does not
  work and something must change · `minor` = advisory. **Severity and verdict are coupled and we check
  it:** a `major` or `blocking` conflict is incompatible with `verdict: feasible`, and a `blocking` one
  requires a refusal verdict. If you spotted a hazard and designed around it, that is `minor` — do not
  inflate it, and do not suppress it either. **Choosing a resin or a protecting group in the
  first place is designing the route, not changing it** — a conflict is something the request forces
  you to work around, not a decision you were always going to make.
- `verdict` is the **worst over modifications**, ordering `feasible < feasible_with_changes <
  infeasible`, with `insufficient_information` dominating all three. A modification is
  `feasible_with_changes` iff you can name a concrete alternative that still achieves the requested
  modification **at the requested site** — moving it to a **different residue**, or dropping it, is a
  different request, not a change. A **coordinate change is not a relocation**: if the requested
  residue still exists in the target and only its index moved because the sequence changed,
  re-indexing it is a valid resolution and the remap belongs in `site_map[].note`.
- An `intent_not_achieved` conflict at `major` downgrades the verdict to `feasible_with_changes` even
  where the chemistry is untouched. That is the one place the ladder is not purely about feasibility.
  **Read `intent` as the design goal, not as a literal string to satisfy** — "improve solubility" is met
  by any PEG, but if that PEG lands on the pharmacophore the request has failed at what it was for, and
  that is the flag.
- `resolved_sequence` is the target **backbone**: one letter per backbone residue, `X` for anything
  without a standard code, each `X` declared in `resolved_annotations`. Side-chain and terminal
  conjugates (lipid, PEG, spacers, sugars, caps) are **not** represented, nor is connectivity. A
  change of stereochemistry alone does not change the letter. For a whole-sequence inversion it is simply the
  reversed string. If you build a full mimic with gem-diaminoalkyl and malonyl termini, declare those
  in `resolved_annotations` and say so in `site_map[].note` — but the reversed string itself does not
  change.
- `site_map` has one entry per **(requested site token, resolved position)** pair, over `modifications`
  only. `parent_features` generate no entries. For `N-term`, `C-term` and `whole sequence`, `residue`
  is `null` and `resolved` echoes the token.
- Report an `order_of_operations` conflict whenever two requested modifications would destroy each
  other under the naive stage order, **even if your own `route` sequences them correctly**. The
  conflict records the hazard; the `route` records your handling of it.
- **Extra conflicts.** Raising a finding we did not expect does not cost points, with three exceptions
  you should know about. A key can mark a kind as *positively wrong* for a case, and asserting one of
  those costs at any severity. Severity has to stay coherent with the verdict — a `major` finding next to
  `verdict: feasible` is a contradiction and is capped. And more than **two kinds beyond what the key
  demands** forfeits the 2/2 on that case, flagged `+indiscriminate` in the reason string: two is
  generous room to be right about something we missed; six is a switch left on. So: raise what you
  believe, rate it honestly, and move the verdict if the finding warrants it. **Use the `kind` enum
  exactly** — a conflict whose `kind` is not one of the seven values above is not read as a finding at
  all, and is reported as `unreadable_conflict_kinds`; a typo is not a free pass. We also report `shotgun_index` and
  `conflicts_per_case`, and we check that each conflict applies to the request it is attached to — a
  correct-sounding conflict about chemistry the request does not contain is worse than raising
  nothing. Extras are reported as
  `unexpected_kinds` and read by a human. We are trying to find out whether you see more than we do; a
  scorer that charged per extra finding would defeat the exercise. No individual finding costs unless
  the key marks that kind positively wrong — what costs is the habit: an incoherent severity, or so
  many kinds at once that the answer stops being an answer.
- `resolved_sequence` letters, one rule: **write the standard one-letter code of the residue that is
  actually there.** A substitution to another standard residue takes that residue's letter (Met→Arg
  becomes `R`). `X` is only for a residue with no standard code — Nle, Aib, a staple residue, a
  threoninol — and every `X` is declared in `resolved_annotations`. Changes that do not change which
  residue it is — D-substitution, N-methylation, a side-chain conjugate — leave the letter alone.
- `site_map`: a multi-position token expands to one entry per position, each echoing the **whole**
  requested token — `"V21,R25"` gives `{"requested": "V21,R25", "resolved": "V21"}` and
  `{"requested": "V21,R25", "resolved": "R25"}`. `both termini` expands to `N-term` and `C-term`.
  `whole sequence` gets one entry echoing the token. `resolved` uses the **parent** letter and index
  where the residue still exists. We check the pairs we expect are present and allow a few extras —
  listing every possible pair is not an answer.
- If a field is genuinely ill-defined for a request, say so in `unknowns`. That beats a confident value.

### What the system has to do

1. **Traceability.** Any claim must be answerable with "which sheet and row, or what inference."
2. **Site validation** against the actual sequence, including index arithmetic under sequence-altering
   modifications.
3. **Order-of-operations planning** over the stages `resin_selection · chain_assembly ·
   on_resin_modification · n_terminal_cap · cleavage · solution_phase · purification · qc`. Order is
   the point. Keep `route` terse, but **use one step per operation and repeat a stage when a stage
   contains two ordered operations** — if the order within a stage matters, that is exactly what we
   want to see.
4. **Conflict detection** — pairwise and higher-order interactions between modifications. This is where
   most of the grade lives.
5. **Calibrated refusal** — "hard but doable", "doable if you change X", "impossible as specified",
   "not enough information" are four different answers.

**On architecture, we are not prescribing one.** The corpus is roughly 13k tokens of cell text — it fits in a prompt
several times over, so retrieval may or may not be the right shape. A deterministic rules engine with
the model used only where judgment is needed is a legitimate answer. So is a tool-calling agent. So is
something else. **If you conclude an agent loop is the wrong shape for this problem, build what you
think is right and argue for it — that argument, made well, scores higher than a loop built because
you assumed we wanted one.**

---

## 3. Measuring it

Work in whatever order suits you. Code freezes 09:00 on Day 3, so the build window is Day 1 afternoon
and Day 2. Scope accordingly.

**One rule, and it is not about pace: an eval case must be committed before you first run the agent
against it.** Write three cases, build the agent, write seven more — fine. Writing the expected answer
after seeing the output is not, and the commit history is what distinguishes them. One file per case and ordinary
commits are all we need — **we read the history ourselves; do not build a tamper-evidence mechanism
you control both ends of.**

Requirements:

- **≥ 6 cases that you wrote**, on top of the 12 supplied ones. Six good ones beat twenty thin ones,
  and we would rather you spent the hours on the chemistry than on volume. Run `score.py expected_dev.jsonl <your_output>.jsonl`
  and the same against your own key; report both, labelled.
- **Run `score.py --validate-key` on your own key and paste the output.** It refuses keys that assert
  nothing — an accepted-verdict list covering everything, a negative control with no expected conflict,
  a blocking conflict with no refusal verdict. A key that fails it is not a measurement.
- **At least one plausible negative control** — correct answer `infeasible` or
  `insufficient_information`. One well-built one is enough; obvious nonsense tests nothing, so make it
  a case a competent-sounding system would wave through.
- **At least two clean cases** — correct answer `feasible` with no `blocking` or `major` conflict.
  (`minor` advisories are fine and do not make a case dirty.)
- **A scrambled-input control** — a valid request with sites permuted onto residues that cannot support
  them. Report the number whatever it is.
- **`score.py` is shipped with this package and is the scorer.** It defines pass, partial pass and
  recall, so the numbers in your report mean what we think they mean. Do not write your own; do read it —
  its docstring is the specification. Four mechanics, and one dependency, to know before you tune anything:
  - A case scores **2** only when the verdict is acceptable *and* the reasoning is: every expected
    conflict kind present at or above its floor severity, every required kind carrying a real
    resolution, nothing the key marks forbidden, and no more than two kinds beyond what the key demands.
  - **A correct verdict on its own pays 1** only where the key expects no conflict, or where at least
    one expected conflict was also found. A bare correct verdict with none of the reasoning behind it
    scores 0 — a constant guess is not an answer.
  - **A `resolution` string reused on three or more cases is a template, not a resolution**, and does
    not satisfy a case that requires one. Reused `description` and `detail` text counts the same way.
  - **A negative control is passed by refusing.** Solving it instead may well be right, but nothing
    mechanical can check that you named a real route, so a non-refusal answer is capped at 1 and goes
    to the hand-read.
  - Two modes need a package — `--validate` needs `jsonschema`, `--audit` needs `openpyxl`
    (`pip install jsonschema openpyxl`). Every other mode is pure standard library.
- **One required ablation, one optional.** Required is *B, no-model*; *A, no-corpus* is worth doing if
  you have time, and is genuinely awkward to define for a deterministic architecture — say so rather
  than forcing a number.
  - *A, no-corpus:* the identical pipeline with every corpus-derived **artifact** removed — prompt text
    and any hand-transcribed table, index or rule derived from the workbook — keeping the request, the
    schema, the model, and only code that encodes no corpus content (sequence parsing, index
    arithmetic, schema validation). This is architecture-neutral on purpose: it asks what the corpus
    adds, whether you put it in a prompt or in a dict.
  - *B, no-model:* every model call replaced by a stub returning `feasible / high / conflicts: []`,
    keeping everything else. **Report B twice — deterministic layer on, and off.**
- **Model calls and tokens per request**, median and worst case, plus one line on what drives the worst
  case. Not dollars.

You do not get to move an expected answer after seeing what your agent did. If a case turns out wrong,
say so and mark it referred, not revised.

**If you run out of time, cut in this order:** the §9 extensions, the no-corpus ablation, then cases
beyond six. **Do not cut the clean-clone check or the README** — those are how we read everything else. Tell us what you cut and why — that is a decision we want to
see you make, not a failure to hide.

---

## 4. What you are given

| Input | Notes |
|---|---|
| `ApexChem_Synthesis_Reactions_by_AminoAcid.xlsx` | 22 sheets: a README, a family master grid, a residue-first index, 15 reaction-family sheets, a reagent checklist, an order-of-operations sheet, an open-decisions sheet, a caveats sheet. Your corpus. It is a transcription of a slide deck and its own caveat sheet rates it "accurate with fixes." |
| `design_requests.jsonl` | 12 design requests, sanitized. Your dev set. Not all are fully answerable from the corpus; finding out which is part of the exercise. |
| `expected_dev.jsonl` | **Our expectations for all 12 dev requests.** Use it to check yourself against us rather than only against your own beliefs. Your own cases are measured too, and reported separately as self-graded. |
| `schema.json`, `score.py` | The output contract and the scorer. Both authoritative. |
| `ApexChem_templates_and_targets.xlsx` | 99 templates; receptor target and class are populated where we have them (62 of 99 carry a receptor class) — you will need the receptor class for at least one case. The **sequence column is a display column and is not machine-parseable**; do not build cases off it, and note that positions quoted inside it may use literature numbering rather than position-in-string. |
| **Two** Anthropic API keys | One for the agent, one for your coding assistant. Report agent tokens from the first only — one key for both makes the per-request number meaningless. We provide them and pay for the tokens. Scoped to this exercise with a spend cap I will name at kickoff. Model choice is yours. |

**Carve-outs.** No partner-priority material, no opioid-receptor peptides, no amylin analogs, no lab
data. None is needed.

---

## 5. Constraints

- **No GPU work.** No structure prediction, docking, MD, training or fine-tuning.
- **Python.** Framework your choice, including none.
- **AI coding assistants are expected.** We will ask which parts you wrote, which you generated, and
  which generated parts you rejected — keep track, that conversation is informative.
- **Internet is fine.** Anything from outside the corpus must be cited, in code or in the report. A
  cited outside source is a good answer; an uncited assertion dressed as corpus fact is not.

---

## 6. Deliverables

1. **A git repository** with real commit history — we read it.
2. **`route-agent` CLI** — `run` for one request, `eval` for the harness.
3. **`EVAL_REPORT.md`** — the `score.py` numbers, the scramble control, the ablation figures,
   model calls per request, and a section titled **"Where this agent fails"** with a case ID per
   failure mode. That section outweighs the pass rate.
4. **`README.md`** — how to run it, the architecture, and the design decisions you rejected and why.
5. **`CORPUS_ERRATA.md`** — every place the workbook does not honour a claim it makes about itself,
   with cell references. It describes its own contents in several places; read those as assertions to
   test. The arithmetic is internally consistent, so that is not where to look. An empty file is an
   answer if you show your method.
6. **`forecasts.json`** — your per-case probabilities and one-line reasons for the held-out set,
   submitted at 09:00 on Day 3 before the run. This is a required deliverable, not an optional step.
7. **A 20-minute presentation** plus 25 minutes of questions, aimed at finding what the work gets
   wrong.

**What is graded that a scorer cannot see, so you know where to spend effort:** the step ordering in
`route`; what you put in `affected` and `unknowns`; whether `CORPUS_ERRATA.md` contains at least one
error that took chemistry to find rather than a script; and — on Day 3 — we run three of the held-out
cases three times each and compare, so pin your model and think about temperature. Come ready to defend decisions and to concede fast when the chemistry says otherwise.

---

## 7. Acceptance criteria

The bar for a complete submission. Missing one is not fatal **except the three marked †** — telling us
which and why beats leaving it out quietly.

- [ ] `route-agent run` produces `schema.json`-valid output for all 12 dev requests without crashing.
- [ ] Every claim carries provenance — `corpus`, `inference`, or `external` for a cited outside source.
- [ ] `route-agent eval` runs end to end and regenerates `EVAL_REPORT.md` using the shipped `score.py`.
- [ ] **†** ≥ 6 self-written cases, at least one negative control and two clean, each committed before its
      first run — an expected answer committed *after* the run it grades is not a measurement.
- [ ] `score.py expected_dev.jsonl <your_output>.jsonl` reported, with `site_map_exact`, `resolved_sequence_exact` and
      `negative_control_recall` alongside the headline — a constant `feasible` stub scores about 0.67
      on the headline alone and zero on those three, which is why all four are reported together.
- [ ] Scramble control reported.
- [ ] The no-model ablation reported, both with the deterministic layer on and with it off.
- [ ] `resolved_sequence`, `resolved_annotations` and `site_map` populated, or filed under `unknowns`.
- [ ] At least one detected protecting-group orthogonality conflict at `major` or above, with a correct
      alternative.
- [ ] `CORPUS_ERRATA.md` exists.
- [ ] **†** `forecasts.json` submitted at the Day 3 freeze, covering all nine held-out cases.
- [ ] **†** Every number you report is reproducible by re-running your own commands — a reported number
      `score.py` does not reproduce is worse than no number. **Reporting nothing is
      worse than reporting a bad number** — a missing measurement reads as a measurement you did not
      want us to see.
- [ ] "Where this agent fails" is populated.
- [ ] Runs from a clean clone on a machine that is not yours.

**†** The three hard stops: no `forecasts.json` at the freeze, an expected answer committed after the
run it grades, and a reported number `score.py` does not reproduce. Those three are not trade-offs you
can declare your way out of.

---

## 8. Schedule

| When | What | Format |
|---|---|---|
| Day 1, 09:00 | Kickoff, corpus walkthrough, questions | 60 min |
| **Day 1, 17:00** | **Checkpoint 1** — where you are | 20 min |
| **Day 2, 17:00** | **Checkpoint 2** — end to end, honest numbers including the bad ones | 20 min |
| **Day 3, 09:00** | **Freeze, then the held-out set** — see below | — |
| Day 3, 16:00 | Final review | 20 + 25 min |

**The held-out set.** At 09:00 your code freezes and you get 9 requests you have not seen. You are told
one number about them — how many of the nine have a refusal, `infeasible` or
`insufficient_information`, as our primary expected verdict — so the
forecast tests your judgment rather than your guess at our base rate. You read them, then **before running, submit for each one a probability that it scores
full marks, with one line of reasoning** — as JSON, `{"<request_id>": {"p": 0.4, "why": "..."}, ...}`. Your agent then runs
them unmodified. We score the results with the same `score.py` and score your forecasts with
`score.py --brier`, which leads with `gain_vs_own_mean` and `gain_vs_best_constant` — those two are the
numbers we read. A flat forecast earns nothing on either, optimistic or pessimistic: a confident flat
p=1.0 can post the best raw Brier on the sheet while predicting nothing at all, which is exactly what
those two numbers expose. Only per-case discrimination pays.

This is announced deliberately. An agent tuned until it passes your own cases will not survive nine it
has never seen, and the nine sentences of reasoning are the part we care most about.

I am available for questions at kickoff and for a short window after. From Day 2 you work from the
corpus. Bring chemistry questions early.

---

## 9. If you finish early

- **Self-critique pass.** A second stage that attacks the first stage's route and tries to refute it.
  Measure whether it changes outcomes — a critic that never overturns anything is not a critic.
- **Campaign batching.** Generate a batch across families and identify which analogs share a
  protecting-group scheme and could run as one campaign. The interesting part is deciding what makes
  two routes compatible enough to batch.
- **Harden your own eval.** Ten more cases designed to break what you just built, and what they found.

---

## 10. How this is judged

**Agent engineering judgment.** Where determinism sits versus where the model reasons, and whether that
boundary was chosen or defaulted into. Whether refusal is a designed path. Whether the harness measures
the thing that matters.

**Scientific reasoning.** Whether you encoded chemistry or pattern-matched vocabulary. Whether you can
tell which of your claims are corpus-grounded and which are yours — the provenance field exists so you
can say so.

**Code quality and rigor.** What a teammate inherits: structure, tests, reproducibility, commit history,
and a README that lets someone else run it.

What will not help: a polished demo with no failure analysis; a framework wrapping a small amount of
thinking; confident output where the corpus does not support an answer.
