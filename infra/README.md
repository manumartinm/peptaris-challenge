# Local observability stack

Langfuse v4 plus Vector, ClickHouse tables owned by this repo, and Grafana.

ClickHouse is shared as a process with Langfuse. Application logs go to a
separate database (`route_agent_observability`). Do not query Langfuse's
internal tables.

## Start

```bash
mkdir -p .observability/logs
cp infra/.env.example infra/.env
docker compose -f infra/docker-compose.yml --env-file infra/.env up -d
```

Wait until `langfuse-web` logs `Ready`.

| UI | URL | Login |
| --- | --- | --- |
| Langfuse | http://localhost:3000 | `dev@localhost` / `changeme` |
| Grafana | http://localhost:3001 | `admin` / `admin` |

Project keys (same as the repo `.env.example`):

- public: `pk-lf-local-route-agent`
- secret: `sk-lf-local-route-agent`
- host: `http://localhost:3000`

Write JSONL logs the stack can tail:

```bash
export ROUTE_AGENT_LOG_DIR=.observability/logs
export ROUTE_AGENT_LOG_FORMAT=json
export ROUTE_AGENT_VERBOSE=2
# optional, local only
export ROUTE_AGENT_TRACE_PAYLOADS=true
uv run route-agent run REQUEST.json --no-model -vv --log-format json
```

Grafana dashboards (folder **Route Agent**, login `admin` / `admin`):

| Dashboard | URL |
| --- | --- |
| Overview | http://localhost:3001/d/route-agent-observability |
| Pipeline | http://localhost:3001/d/route-agent-pipeline |
| Errors & Jobs | http://localhost:3001/d/route-agent-errors |
| LLM | http://localhost:3001/d/route-agent-llm |
| Run Explorer | http://localhost:3001/d/route-agent-explorer |

Filter any of them by `run_id`, `request_id`, or `job_id`. The same ids
appear on the Langfuse trace named `route_agent_run`.

## Diagnose a run

1. Grab `run_id` from stderr JSON or the `X-Run-Id` response header.
2. Langfuse: filter session/metadata by `request_id` or `run_id`.
3. Grafana variable boxes: paste the id.
4. ClickHouse:

```sql
SELECT timestamp, level, event, component, duration_ms, message
FROM route_agent_observability.logs
WHERE run_id = 'YOUR_RUN_ID'
ORDER BY timestamp
```

## Stop

```bash
docker compose -f infra/docker-compose.yml --env-file infra/.env down
```

Add `-v` to wipe volumes (Langfuse traces, ClickHouse logs, Grafana).

## Ports

| Service | Port | Bound |
| --- | --- | --- |
| Langfuse UI | 3000 | all interfaces |
| Grafana | 3001 | localhost |
| MinIO S3 | 9090 | all interfaces |
| MinIO console | 9091 | localhost |
| Worker | 3030 | localhost |
| Postgres | 5432 | localhost |
| ClickHouse HTTP | 8123 | localhost |
| ClickHouse native | 9000 | localhost |
| Redis | 6379 | localhost |

Secrets in `infra/.env` are for local use only.

The pipeline is fail-open: Vector, ClickHouse, Grafana, or Langfuse being
down does not fail `route-agent run`. Vector resumes from the JSONL file
when ClickHouse comes back.

## Smoke

```bash
chmod +x infra/smoke.sh
./infra/smoke.sh
```

That script starts Compose, runs one `--no-model` request, checks that
ClickHouse has pipeline rows, and pings Grafana. For a live Langfuse check
(one `route_agent_run` with a generation) after the stack is up:

```bash
uv run pytest tests/unit/llm/test_langfuse_live.py -m live
```
