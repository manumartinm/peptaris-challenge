# EVAL_REPORT

Official `data/score.py` against the provided expected key (dev set only).

**Headline:** 18/24 (0.75)

## Official metrics

- `site_map_exact`: 1.0
- `resolved_sequence_exact`: 1.0
- `negative_control_recall`: 0.5
- `conflict_recall`: 0.8333
- `clean_case_precision`: 1.0

## Model calls and tokens

- median calls: 5.0
- worst calls: 9 (`REQ-04`)
- median tokens (in+out): 158620.0
- worst tokens (in+out): 371278 (`REQ-07`)

## Schema validation

`score.py --validate` checked True with 0 invalid object(s).

## Where this agent fails

- `REQ-05`: 0/2 miss unexpected=['protecting_group_orthogonality']
- `REQ-08`: 0/2 miss unexpected=['protecting_group_orthogonality']
- `REQ-12`: 0/2 miss unexpected=['reagent_incompatibility']

## Scope limits

Self-authored expected key, scramble control, and ablations (including no-model ablation as a scored comparison) were **not run**. No numbers are invented for those controls.

This report covers only `design_requests.jsonl` vs `expected_dev.jsonl` when those files are passed to `route-agent eval`.
