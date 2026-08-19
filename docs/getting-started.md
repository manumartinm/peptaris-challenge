# Getting started

This guide covers local development, an installed wheel, credentials,
configuration, the CLI, the jobs API, and common failures. The shortest offline
path is:

```bash
uv sync --frozen
uv run route-agent doctor --no-model
uv run route-agent run request.json --no-model --explain
```

## Requirements

| Component | Required for |
| --- | --- |
| Python 3.12+ | CLI, API, and core pipeline |
| `uv` | Source development and reproducible installs |
| Node.js + npm | Trace Explorer only |
| Provider API key | Live compatibility, intent, and final-judge calls |
| `BOLTZ_API_KEY` | Optional 3D structure prediction |
| Docker Compose | Optional local observability stack |

RDKit is a Python dependency and is installed by `uv` or the wheel. The first
install can take several minutes because of scientific dependencies.

## Source checkout

```bash
uv sync --frozen --group dev
uv run route-agent --version
uv run route-agent doctor --no-model
```

Use `uv run` for all Python entry points while working from source. No package
activation is required.

The checkout automatically reads `<repo>/.env`. Start from the documented
template:

```bash
cp .env.example .env
```

Do not commit `.env`.

## Wheel or pipx install

Build and inspect the distributable:

```bash
uv build
uv run twine check --strict dist/*
uv run python scripts/inspect_dist.py dist
```

Install the local wheel in an isolated pipx environment:

```bash
pipx install dist/peptaris_route_agent-*.whl
route-agent doctor --no-model
```

After publication, replace the wheel path with `peptaris-route-agent`.

The wheel includes all read-only runtime resources:

- family/process profiles;
- molecular fragment definitions;
- parent-peptide target templates;
- public request and verdict schemas;
- the official evaluation scorer.

An installed wheel does not depend on the repository's `data/` directory.

## Credentials and model selection

Interactive work:

```bash
route-agent config set-api-key anthropic
route-agent config show
route-agent doctor
```

The keyring prompt is hidden. `config show` reports whether credentials exist
but never prints them.

CI and headless environments should use environment variables:

```bash
export ANTHROPIC_API_KEY='...'
export ROUTE_AGENT_MODEL='anthropic/claude-sonnet-4-5'
```

OpenAI is also supported:

```bash
export OPENAI_API_KEY='...'
route-agent run request.json --model openai/gpt-5.6-terra --reasoning high
```

Credential precedence is:

1. the environment variable for the selected provider;
2. the system keyring;
3. absent.

`--model` and `--reasoning` apply to one invocation. Their environment defaults
are `ROUTE_AGENT_MODEL` and `ROUTE_AGENT_REASONING_EFFORT`.

## Create a request

`route-agent run` accepts one JSON object, not JSONL. A minimal request:

```json
{
  "request_id": "REQ-DEMO",
  "parent_name": "glucagon",
  "sequence": "HSQGTFTSDYSKYLDSRRAQDFVQWLMNT",
  "parent_c_terminus": "free_acid",
  "residue_annotations": {},
  "parent_features": [],
  "modifications": [
    {
      "family": "lipidation",
      "site": "K12",
      "detail": "C18-diacid via 2xAEEA-gGlu spacer"
    }
  ],
  "intent": "extend plasma half-life via albumin binding"
}
```

Supported modification-family enum values:

```text
spps_foundation, special_residues, n_methylation, c_term_amidation,
n_term_acetylation, lipidation, pegylation, glycosylation, cyclization,
hydrocarbon_stapling, disulfide, biaryl_bisalkylation, aza_peptide,
retro_inverso, charge_hybrids
```

Site tokens can name a residue (`K12`), multiple residues (`V21,R25`), a
terminus, or a whole-sequence transform where the family permits it. Every `X`
in `sequence` must have an `X{position}` entry in `residue_annotations`.

The machine-readable contract is packaged as `request_schema.json`. Examples
for all supported families are in `data/design_requests.jsonl`.

## Run the CLI

Validate input without producing a final verdict:

```bash
uv run route-agent validate request.json --no-model --explain
```

Run offline:

```bash
uv run route-agent run request.json \
  --no-model \
  --trace-dir traces \
  --explain \
  -o verdict.json
```

Run with live judgment:

```bash
uv run route-agent run request.json \
  --model anthropic/claude-sonnet-4-5 \
  --reasoning medium \
  --trace-dir traces \
  --explain \
  -o verdict.json
```

Output channels are a stable contract:

- stdout: the public `RouteVerdict` JSON when `-o` is absent;
- stderr: logs and `--explain`;
- `--trace-dir`: the internal `PipelineTrace`.

This separation permits:

```bash
route-agent run request.json --no-model 2>run.log | jq '.verdict'
```

## Run Trace Explorer

Terminal 1:

```bash
uv run route-agent-api
```

Terminal 2:

```bash
cd trace-viewer
npm ci
npm run dev
```

Open the URL printed by Vite, normally `http://127.0.0.1:5173`. See
[Trace Explorer](trace-explorer.md) for the workflow and API contract.

## Call the API directly

The local API binds to `127.0.0.1:8000`:

```bash
curl http://127.0.0.1:8000/api/health

curl -X POST \
  'http://127.0.0.1:8000/api/jobs?no_model=true' \
  -H 'Content-Type: application/json' \
  --data-binary @request.json
```

The response is `202 Accepted` with `job_id`, `request_id`, `status`, and
`run_id`. Poll and then fetch the trace:

```bash
curl http://127.0.0.1:8000/api/jobs/JOB_ID
curl http://127.0.0.1:8000/api/jobs/JOB_ID/trace
```

A second submission while a job is queued or running returns `409 Conflict`.

## Configuration reference

### Model and external services

| Variable | Default | Meaning |
| --- | --- | --- |
| `ROUTE_AGENT_MODEL` | `anthropic/claude-sonnet-4-5` | LiteLLM model |
| `ROUTE_AGENT_REASONING_EFFORT` | `medium` | Provider reasoning setting |
| `ANTHROPIC_API_KEY` | unset | Anthropic credential |
| `OPENAI_API_KEY` | unset | OpenAI credential |
| `BOLTZ_API_KEY` | unset | Optional Boltz 3D credential |
| `ROUTE_AGENT_BOLTZ_TIMEOUT` | `180` | Boltz request deadline in seconds |
| `ROUTE_AGENT_CHECK_TIMEOUT` | `180` | Compatibility-check deadline |
| `JOURNAL_ALLOWLIST` | curated journal hosts | Comma-separated citation hosts |

### Molecular behavior

| Variable | Default | Meaning |
| --- | --- | --- |
| `ROUTE_AGENT_MOLECULAR_PH` | `7.4` | Descriptor pH |
| `ROUTE_AGENT_MOLECULAR_SKIP_3D` | `false` | Skip Boltz 3D |
| `ROUTE_AGENT_MOLECULAR_CONFORMERS` | `20` | Molecular configuration value |
| `ROUTE_AGENT_MOLECULAR_SEED` | `17` | Reproducibility seed |
| `ROUTE_AGENT_MOLECULAR_TIMEOUT` | `60` | Local molecular timeout |
| `ROUTE_AGENT_MOLECULAR_MAX_HEAVY` | `500` | Heavy-atom limit |

3D is omitted when `--no-model` is active, the Boltz key is missing, or
`ROUTE_AGENT_MOLECULAR_SKIP_3D=true`. RDKit 2D checks and descriptors still run.

### Paths and packaged resources

| Variable | Meaning |
| --- | --- |
| `ROUTE_AGENT_ENV_FILE` | Additional explicit `.env` path |
| `ROUTE_AGENT_CACHE_DIR` | Writable cache root |
| `ROUTE_AGENT_DATA_DIR` | Writable application-data root |
| `ROUTE_AGENT_CONFIG_DIR` | Writable config/key metadata root |
| `ROUTE_AGENT_RESEARCH_ROOT` | Literature sandbox and cache |
| `ROUTE_AGENT_EXTRACTED_FAMILIES` | Override packaged family profiles |
| `ROUTE_AGENT_TARGETS` | Override packaged target workbook |
| `ROUTE_AGENT_FRAGMENTS` | Override packaged molecular fragments |
| `ROUTE_AGENT_SCHEMA` | Override verdict schema |
| `ROUTE_AGENT_REQUEST_SCHEMA` | Override request schema |
| `ROUTE_AGENT_SCORE_PY` | Override official scorer |

Resource overrides are intended for controlled development. A mismatch between
`data/` and packaged resources can change behavior and evaluation results.

### Logging and tracing

| Variable | Meaning |
| --- | --- |
| `ROUTE_AGENT_LOG_DIR` | Directory for persistent JSONL logs |
| `ROUTE_AGENT_LOG_FORMAT` | `text` or `json` |
| `ROUTE_AGENT_VERBOSE` | Default verbosity |
| `ROUTE_AGENT_TRACE_PAYLOADS` | Include redacted prompt/response payloads |
| `LANGFUSE_PUBLIC_KEY` | Optional Langfuse public key |
| `LANGFUSE_SECRET_KEY` | Optional Langfuse secret |
| `LANGFUSE_HOST` | Langfuse endpoint |

Keep `ROUTE_AGENT_TRACE_PAYLOADS=false` outside controlled local debugging.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `doctor` reports no provider key | Set the matching environment variable or keyring entry; otherwise use `--no-model` |
| Result is `insufficient_information` offline | Expected when compatibility, intent, or final judgment requires a model |
| No 3D block in the trace | Set `BOLTZ_API_KEY`; ensure `--no-model` and `ROUTE_AGENT_MOLECULAR_SKIP_3D` are off |
| API returns `409` on submit | Wait for the active single-worker job to finish |
| API returns `404` after restart | In-memory job state was lost; use `/api/traces` or the persisted trace file |
| UI cannot reach the API | Start `route-agent-api` on port 8000 and use the Vite dev server on port 5173 |
| Resource path fails after pipx install | Run `route-agent doctor`; do not point overrides at checkout-only files |
| JSON appears mixed with logs | Capture stdout and stderr separately; `--explain` is intentionally stderr-only |
| Live call appears hung | Reduce `ROUTE_AGENT_CHECK_TIMEOUT`; the walker marks timed-out checks as unknown |

For observability-stack issues, use [`infra/README.md`](../infra/README.md).
