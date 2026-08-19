# route-agent

Synthesizability checker CLI for designed peptide analogs.

User-facing setup lives in [`README.md`](README.md). This file is the
contributor map: architecture, invariants, and how to run the suite.

## Commands

```bash
uv sync
uv run ruff check src tests scripts
uv run ruff format src tests scripts
uv run mypy src tests
uv run pytest tests -m "not live and not eval"
uv run route-agent doctor --no-model
uv run route-agent run REQUEST.json --no-model --explain
uv run route-agent-api
```

Exit codes: `0` ok, `1` bad input, `2` validation/agent failure (diagnostic
commands), `3` infrastructure. `run` exits `0` whenever it emits a schema-valid
RouteVerdict, including refusals.

Local Langfuse is optional and lives in `infra/`.

## Package map

| Package | Role |
| --- | --- |
| `src/route_agent/` | Core chemistry, pipeline, observers, composition wiring |
| `src/route_agent/composition/` | Shared factories for parser, runtime, walker, post-graph, pipeline |
| `src/route_agent/services/` | Request loading without CLI/HTTP concerns |
| `src/route_agent_cli/` | Click app, commands, `--explain`, keyring |
| `src/route_agent_api/` | FastAPI jobs adapter; one in-memory job per app |
| `src/route_agent_api/jobs/` | Store, phase mapping, and on-disk trace index |
| `src/route_agent/credentials.py` | Keyring store; never logs secrets |
| `src/route_agent/paths.py` | Packaged resources and XDG locations |
| `src/route_agent/doctor.py` | Configuration checks |
| `src/route_agent/pipeline.py` | `validate → walk → post_graph → judge → assemble` |
| `src/route_agent/observe.py` | PipelineObserver protocol (in-process events) |
| `src/route_agent/observability/` | Structured logging and correlation ids |
| `src/route_agent_cli/explain.py` | `--explain` terminal observers |
| `src/route_agent/evaluation.py` | Dev-set JSONL runner; subprocesses packaged `score.py` |
| `src/route_agent/trace.py` | Atomic internal traces (`traces/{request_id}.trace.json`) |
| `src/route_agent/settings.py` | model, Langfuse, keys, paths |
| `src/route_agent/models/` | Pydantic contracts including `events` and `trace` |
| `src/route_agent/parser/` | Validation pipeline |
| `src/route_agent/corpus.py` | Family profiles and parent-peptide targets |
| `src/route_agent/conflict/` | Conflict-tree walker, ledger, pending-handle resolution |
| `src/route_agent/verdict/` | Route reconstruction, conflicts, verdict ladder |
| `src/route_agent/molecular/` | Product state, builder, fragments, analysis |
| `src/route_agent/post_graph/` | Survivor 2D/3D, intent, winner, `final_judge` |
| `src/route_agent/agent/` | Deep Agent runtime, semantic `CompatCache` categories |
| `src/route_agent/llm/` | LiteLLM client, call aggregation, Langfuse tracer/generations |
| `src/route_agent/literature/` | Native provider web tools and citation audit |
| `src/route_agent/resources/` | Wheel copies of runtime artifacts |

Core must not import `route_agent_cli` or `route_agent_api`. The API must not
import the CLI. Both adapters construct the pipeline through
`route_agent.composition.wiring`.

**Structure.** Group by concept, not by class. A module is one cohesive concept.
Split when a module holds two concepts that share no state. Inject dependencies
in `__init__`. No module-level clients.

**Naming.** Every function is a verb plus its object. Private methods keep the
leading underscore.

## Observability names

| Name | Meaning |
| --- | --- |
| `observe` | In-process `PipelineEvent` stream for `--explain` and the jobs UI |
| `observability` | Loguru logs, correlation ids, payload redaction |
| `Langfuse generation` | One external LLM observation per real model attempt |
| `trace` | Persisted `PipelineTrace` JSON on disk |

Cache hits do not open a Langfuse generation. Do not combine LangChain
`CallbackHandler` tracing with `LangfuseRun.generation()` for the same call.

## Artifact map

| Artifact | Producer | Consumer |
| --- | --- | --- |
| `data/extracted_families.json` | `notebooks/extract_families.ipynb` | `CorpusRepository`, packaged into the wheel |
| `data/molecular_fragments.json` | authored | `FragmentCatalog` |
| `data/schema.json` | challenge | public RouteVerdict + `debug eval` |
| `data/request_schema.json` | generated from `DesignRequest` | public request contract |
| `data/score.py` | official, do not edit | `debug eval` / checkout tests |
| `src/route_agent/resources/score.py` | packaged copy of the official scorer | installed `score_py_path()` |
| `data/design_requests.jsonl` + `expected_dev.jsonl` | official 12-case set | `debug eval` |
| `EVAL_REPORT.md` | `debug eval` / `score.py` | humans; do not edit by hand |
| `traces/{id}.trace.json` | `route-agent run` | trace-viewer |

`paths.py` prefers packaged `resources/` and falls back to `data/` in a
checkout. Do not silently unify those copies; a drift can change eval scores.

## Domain glossary

- **site**: requested location (`K12`, `N-term`).
- **process_id**: corpus process identifier on `AgentCandidate.process`.
- **ledger / state output**: chemistry notebook on `State.output` (`protected`, `free_amines`, `history`, …). See `StateLedger`.
- **state_categories_present**: coarse chemical facts derived from the ledger (protecting-group families, free amines, catalysts, topology class, history processes). Used by `CompatCache` with `(process, site, categories)`.
- **conflict**: schema `RouteConflict`.
- **unknown**: something the engine or agent could not decide.
- **degraded**: not a chemistry failure. Timeouts and invoke errors stay degraded and leave the frontier.

## Deterministic vs model

The model does **not** decide index arithmetic, site validity, enums,
severity/verdict coherence, or whether a corpus row exists. The Agent never
writes `verdict`.

## TDD and eval integrity

Red test → minimal implementation → green. Do not edit `data/score.py`. Do not
edit expected keys after observing outputs. `eval` covers only the official
12-case dev set.
