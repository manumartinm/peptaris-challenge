#!/usr/bin/env bash
# Local observability smoke: Compose + one --no-model run + ClickHouse + Grafana.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p .observability/logs
if [[ ! -f infra/.env ]]; then
  cp infra/.env.example infra/.env
fi

docker compose -f infra/docker-compose.yml --env-file infra/.env up -d
ready=0
for _ in $(seq 1 90); do
  if curl -fsS http://127.0.0.1:8123/ping >/dev/null 2>&1 \
    && curl -fsS http://127.0.0.1:3001/api/health >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done
if [[ "$ready" -ne 1 ]]; then
  echo "ClickHouse or Grafana did not become ready" >&2
  exit 1
fi

export ROUTE_AGENT_LOG_DIR="$ROOT/.observability/logs"
export ROUTE_AGENT_LOG_FORMAT=json
export ROUTE_AGENT_VERBOSE=2
export ROUTE_AGENT_MOLECULAR_SKIP_3D=true
uv run python - <<'PY'
import json
from pathlib import Path
src = Path("data/design_requests.jsonl").read_text(encoding="utf-8").splitlines()[0]
Path("/tmp/route-agent-smoke.json").write_text(src + "\n", encoding="utf-8")
print(json.loads(src)["request_id"])
PY
uv run route-agent run /tmp/route-agent-smoke.json --no-model --log-format json -vv \
  -o /tmp/route-agent-smoke-verdict.json

# Vector batches every 2s; wait for ingest.
sleep 4
curl -fsS "http://127.0.0.1:8123/?user=clickhouse&password=clickhouse" \
  --data-binary "SELECT count() FROM route_agent_observability.logs WHERE event IN ('command_start','pipeline_start','pipeline_complete')" \
  | grep -E '^[1-9]'

curl -fsS http://127.0.0.1:3001/api/health
echo
echo "Grafana dashboard: http://localhost:3001/d/route-agent-observability"
echo "Langfuse live smoke (optional): uv run pytest tests/unit/llm/test_langfuse_live.py -m live"
