"""Write provisioned Grafana dashboards. Run from this directory."""

from __future__ import annotations

import json
from pathlib import Path

DS = {"type": "grafana-clickhouse-datasource", "uid": "route-agent-clickhouse"}
FILTER = (
    "$__timeFilter(timestamp) "
    "AND (empty('${run_id:raw}') OR run_id = '${run_id:raw}') "
    "AND (empty('${request_id:raw}') OR request_id = '${request_id:raw}') "
    "AND (empty('${job_id:raw}') OR job_id = '${job_id:raw}')"
)
LINKS = [
    {
        "asDropdown": True,
        "icon": "dashboard",
        "includeVars": True,
        "keepTime": True,
        "tags": ["route-agent"],
        "title": "Route Agent",
        "type": "dashboards",
    }
]


def templating() -> dict[str, object]:
    boxes = []
    for name, label in (
        ("run_id", "run_id"),
        ("request_id", "request_id"),
        ("job_id", "job_id"),
    ):
        boxes.append(
            {
                "current": {"selected": False, "text": "", "value": ""},
                "label": label,
                "name": name,
                "options": [],
                "query": "",
                "skipUrlSync": False,
                "type": "textbox",
            }
        )
    return {"list": boxes}


def sql_target(raw_sql: str, *, timeseries: bool = False) -> dict[str, object]:
    return {
        "datasource": DS,
        "editorType": "sql",
        "format": 0 if timeseries else 1,
        "queryType": "timeseries" if timeseries else "table",
        "rawSql": raw_sql,
    }


def panel(
    pid: int,
    title: str,
    ptype: str,
    x: int,
    y: int,
    w: int,
    h: int,
    sql: str,
    *,
    timeseries: bool = False,
    description: str = "",
    options: dict[str, object] | None = None,
    field_config: dict[str, object] | None = None,
) -> dict[str, object]:
    item: dict[str, object] = {
        "datasource": DS,
        "description": description,
        "fieldConfig": field_config
        or {"defaults": {}, "overrides": []},
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "id": pid,
        "targets": [sql_target(sql, timeseries=timeseries)],
        "title": title,
        "type": ptype,
    }
    if options is not None:
        item["options"] = options
    return item


def stat_opts(calc: str = "lastNotNull") -> dict[str, object]:
    return {
        "colorMode": "value",
        "graphMode": "area",
        "justifyMode": "auto",
        "orientation": "auto",
        "reduceOptions": {"calcs": [calc], "fields": "", "values": False},
        "textMode": "auto",
    }


def dashboard(
    *,
    uid: str,
    title: str,
    description: str,
    tags: list[str],
    panels: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "annotations": {"list": []},
        "description": description,
        "editable": True,
        "fiscalYearStartMonth": 0,
        "graphTooltip": 1,
        "id": None,
        "links": LINKS,
        "liveNow": False,
        "panels": panels,
        "refresh": "10s",
        "schemaVersion": 39,
        "tags": tags,
        "templating": templating(),
        "time": {"from": "now-6h", "to": "now"},
        "title": title,
        "uid": uid,
        "version": 1,
    }


def overview() -> dict[str, object]:
    return dashboard(
        uid="route-agent-observability",
        title="Route Agent / Overview",
        description="Operational snapshot: runs, errors, latency, and volume.",
        tags=["route-agent", "overview"],
        panels=[
            panel(
                1,
                "Runs",
                "stat",
                0,
                0,
                4,
                4,
                f"SELECT uniqExact(run_id) FROM route_agent_observability.logs WHERE {FILTER}",
                description="Distinct run_id in the selected window.",
                options=stat_opts(),
            ),
            panel(
                2,
                "Errors",
                "stat",
                4,
                0,
                4,
                4,
                f"SELECT count() FROM route_agent_observability.logs WHERE level IN ('ERROR','CRITICAL') AND {FILTER}",
                options=stat_opts(),
                field_config={
                    "defaults": {
                        "thresholds": {
                            "mode": "absolute",
                            "steps": [
                                {"color": "green", "value": None},
                                {"color": "red", "value": 1},
                            ],
                        }
                    },
                    "overrides": [],
                },
            ),
            panel(
                3,
                "Failed jobs",
                "stat",
                8,
                0,
                4,
                4,
                f"SELECT count() FROM route_agent_observability.logs WHERE event = 'job_failed' AND {FILTER}",
                options=stat_opts(),
                field_config={
                    "defaults": {
                        "thresholds": {
                            "mode": "absolute",
                            "steps": [
                                {"color": "green", "value": None},
                                {"color": "orange", "value": 1},
                            ],
                        }
                    },
                    "overrides": [],
                },
            ),
            panel(
                4,
                "Avg pipeline",
                "stat",
                12,
                0,
                4,
                4,
                f"SELECT avg(duration_ms) FROM route_agent_observability.logs WHERE event = 'pipeline_complete' AND {FILTER}",
                options=stat_opts("mean"),
                field_config={
                    "defaults": {"unit": "ms", "decimals": 0},
                    "overrides": [],
                },
            ),
            panel(
                5,
                "LLM cost",
                "stat",
                16,
                0,
                4,
                4,
                f"SELECT sum(JSONExtractFloat(extra, 'cost_usd')) FROM route_agent_observability.logs WHERE {FILTER}",
                options=stat_opts("sum"),
                field_config={
                    "defaults": {"unit": "currencyUSD", "decimals": 4},
                    "overrides": [],
                },
            ),
            panel(
                6,
                "LLM tokens",
                "stat",
                20,
                0,
                4,
                4,
                f"SELECT sum(JSONExtractInt(extra, 'prompt_tokens') + JSONExtractInt(extra, 'completion_tokens')) FROM route_agent_observability.logs WHERE event = 'llm_generation' AND {FILTER}",
                options=stat_opts("sum"),
                field_config={"defaults": {"unit": "short"}, "overrides": []},
            ),
            panel(
                7,
                "Log volume",
                "timeseries",
                0,
                4,
                12,
                8,
                f"SELECT toStartOfMinute(timestamp) AS time, count() AS logs FROM route_agent_observability.logs WHERE {FILTER} GROUP BY time ORDER BY time",
                timeseries=True,
                field_config={
                    "defaults": {
                        "custom": {"drawStyle": "line", "fillOpacity": 15, "lineWidth": 2}
                    },
                    "overrides": [],
                },
            ),
            panel(
                8,
                "Errors over time",
                "timeseries",
                12,
                4,
                12,
                8,
                f"SELECT toStartOfMinute(timestamp) AS time, count() AS errors FROM route_agent_observability.logs WHERE level IN ('ERROR','CRITICAL') AND {FILTER} GROUP BY time ORDER BY time",
                timeseries=True,
                field_config={
                    "defaults": {
                        "color": {"mode": "fixed", "fixedColor": "red"},
                        "custom": {"drawStyle": "bars", "fillOpacity": 60},
                    },
                    "overrides": [],
                },
            ),
            panel(
                9,
                "Recent runs",
                "table",
                0,
                12,
                24,
                10,
                f"""
SELECT
  run_id,
  any(request_id) AS request_id,
  any(job_id) AS job_id,
  any(source) AS source,
  any(command) AS command,
  min(timestamp) AS started_at,
  max(timestamp) AS finished_at,
  count() AS logs,
  countIf(level IN ('ERROR','CRITICAL')) AS errors,
  maxIf(duration_ms, event = 'pipeline_complete') AS pipeline_ms,
  anyLastIf(status, event = 'pipeline_complete') AS verdict
FROM route_agent_observability.logs
WHERE run_id IS NOT NULL AND {FILTER}
GROUP BY run_id
ORDER BY started_at DESC
LIMIT 50
""".strip(),
            ),
        ],
    )


def pipeline() -> dict[str, object]:
    return dashboard(
        uid="route-agent-pipeline",
        title="Route Agent / Pipeline",
        description="Stage lifecycle, walk, post-graph, and verdicts.",
        tags=["route-agent", "pipeline"],
        panels=[
            panel(
                1,
                "Pipelines completed",
                "stat",
                0,
                0,
                6,
                4,
                f"SELECT count() FROM route_agent_observability.logs WHERE event = 'pipeline_complete' AND {FILTER}",
                options=stat_opts(),
            ),
            panel(
                2,
                "p95 pipeline",
                "stat",
                6,
                0,
                6,
                4,
                f"SELECT quantile(0.95)(duration_ms) FROM route_agent_observability.logs WHERE event = 'pipeline_complete' AND {FILTER}",
                options=stat_opts(),
                field_config={"defaults": {"unit": "ms", "decimals": 0}, "overrides": []},
            ),
            panel(
                3,
                "Walks",
                "stat",
                12,
                0,
                6,
                4,
                f"SELECT count() FROM route_agent_observability.logs WHERE event = 'walk_complete' AND {FILTER}",
                options=stat_opts(),
            ),
            panel(
                4,
                "Verdicts",
                "stat",
                18,
                0,
                6,
                4,
                f"SELECT uniqExact(status) FROM route_agent_observability.logs WHERE event = 'pipeline_complete' AND {FILTER}",
                options=stat_opts(),
            ),
            panel(
                5,
                "Pipeline duration",
                "timeseries",
                0,
                4,
                12,
                8,
                f"SELECT timestamp AS time, duration_ms FROM route_agent_observability.logs WHERE event = 'pipeline_complete' AND duration_ms IS NOT NULL AND {FILTER} ORDER BY time",
                timeseries=True,
                field_config={"defaults": {"unit": "ms"}, "overrides": []},
            ),
            panel(
                6,
                "Verdict mix",
                "piechart",
                12,
                4,
                12,
                8,
                f"SELECT if(empty(status), 'unknown', status) AS verdict, count() AS n FROM route_agent_observability.logs WHERE event = 'pipeline_complete' AND {FILTER} GROUP BY verdict ORDER BY n DESC",
                options={"legend": {"displayMode": "table", "placement": "right", "values": ["value", "percent"]}},
            ),
            panel(
                7,
                "Stage activity",
                "table",
                0,
                12,
                12,
                9,
                f"""
SELECT
  stage,
  countIf(JSONExtractString(extra, 'kind') = 'stage_started' OR event = 'pipeline_event_stage_started') AS started,
  countIf(JSONExtractString(extra, 'kind') = 'stage_finished' OR event = 'pipeline_event_stage_finished') AS finished,
  avg(duration_ms) AS avg_ms
FROM route_agent_observability.logs
WHERE stage IS NOT NULL AND {FILTER}
GROUP BY stage
ORDER BY stage
""".strip(),
            ),
            panel(
                8,
                "Latency by event",
                "table",
                12,
                12,
                12,
                9,
                f"SELECT event, count() AS n, avg(duration_ms) AS avg_ms, quantile(0.95)(duration_ms) AS p95_ms, max(duration_ms) AS max_ms FROM route_agent_observability.logs WHERE duration_ms IS NOT NULL AND {FILTER} GROUP BY event ORDER BY avg_ms DESC LIMIT 25",
            ),
            panel(
                9,
                "Walk checks",
                "table",
                0,
                21,
                24,
                9,
                f"""
SELECT
  timestamp,
  run_id,
  request_id,
  event,
  JSONExtractString(extra, 'process') AS process,
  JSONExtractString(extra, 'family') AS family,
  JSONExtractString(extra, 'site') AS site,
  status,
  JSONExtract(extra, 'passed', 'Nullable(String)') AS passed
FROM route_agent_observability.logs
WHERE event IN ('walk_start','walk_stage_start','walk_check_start','walk_check_done','walk_stage_done','walk_complete')
  AND {FILTER}
ORDER BY timestamp DESC
LIMIT 200
""".strip(),
            ),
        ],
    )


def errors() -> dict[str, object]:
    return dashboard(
        uid="route-agent-errors",
        title="Route Agent / Errors & Jobs",
        description="Failures, API job lifecycle, and noisy components.",
        tags=["route-agent", "errors"],
        panels=[
            panel(
                1,
                "Error logs",
                "stat",
                0,
                0,
                6,
                4,
                f"SELECT count() FROM route_agent_observability.logs WHERE level IN ('ERROR','CRITICAL') AND {FILTER}",
                options=stat_opts(),
                field_config={
                    "defaults": {
                        "thresholds": {
                            "mode": "absolute",
                            "steps": [
                                {"color": "green", "value": None},
                                {"color": "red", "value": 1},
                            ],
                        }
                    },
                    "overrides": [],
                },
            ),
            panel(
                2,
                "Jobs queued",
                "stat",
                6,
                0,
                6,
                4,
                f"SELECT count() FROM route_agent_observability.logs WHERE event = 'job_queued' AND {FILTER}",
                options=stat_opts(),
            ),
            panel(
                3,
                "Jobs completed",
                "stat",
                12,
                0,
                6,
                4,
                f"SELECT count() FROM route_agent_observability.logs WHERE event = 'job_completed' AND {FILTER}",
                options=stat_opts(),
            ),
            panel(
                4,
                "Jobs failed",
                "stat",
                18,
                0,
                6,
                4,
                f"SELECT count() FROM route_agent_observability.logs WHERE event = 'job_failed' AND {FILTER}",
                options=stat_opts(),
            ),
            panel(
                5,
                "Errors by component",
                "bargauge",
                0,
                4,
                12,
                8,
                f"SELECT component, count() AS n FROM route_agent_observability.logs WHERE level IN ('ERROR','CRITICAL') AND {FILTER} GROUP BY component ORDER BY n DESC LIMIT 15",
                options={"displayMode": "gradient", "orientation": "horizontal", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": True}},
            ),
            panel(
                6,
                "Job status over time",
                "timeseries",
                12,
                4,
                12,
                8,
                f"SELECT toStartOfMinute(timestamp) AS time, event, count() AS n FROM route_agent_observability.logs WHERE event IN ('job_queued','job_running','job_completed','job_failed') AND {FILTER} GROUP BY time, event ORDER BY time",
                timeseries=True,
            ),
            panel(
                7,
                "Error stream",
                "table",
                0,
                12,
                24,
                12,
                f"""
SELECT
  timestamp,
  level,
  component,
  event,
  run_id,
  request_id,
  job_id,
  status,
  message,
  JSONExtractString(extra, 'error_type') AS error_type,
  JSONExtractString(extra, 'error') AS error
FROM route_agent_observability.logs
WHERE level IN ('ERROR','CRITICAL','WARNING') AND {FILTER}
ORDER BY timestamp DESC
LIMIT 200
""".strip(),
            ),
        ],
    )


def llm() -> dict[str, object]:
    return dashboard(
        uid="route-agent-llm",
        title="Route Agent / LLM",
        description="Generations, tokens, cost, cache, and model latency.",
        tags=["route-agent", "llm"],
        panels=[
            panel(
                1,
                "Generations",
                "stat",
                0,
                0,
                6,
                4,
                f"SELECT count() FROM route_agent_observability.logs WHERE event = 'llm_generation' AND {FILTER}",
                options=stat_opts(),
            ),
            panel(
                2,
                "Cost USD",
                "stat",
                6,
                0,
                6,
                4,
                f"SELECT sum(JSONExtractFloat(extra, 'cost_usd')) FROM route_agent_observability.logs WHERE {FILTER}",
                options=stat_opts("sum"),
                field_config={"defaults": {"unit": "currencyUSD", "decimals": 4}, "overrides": []},
            ),
            panel(
                3,
                "Tokens in+out",
                "stat",
                12,
                0,
                6,
                4,
                f"SELECT sum(JSONExtractInt(extra, 'prompt_tokens') + JSONExtractInt(extra, 'completion_tokens')) FROM route_agent_observability.logs WHERE event = 'llm_generation' AND {FILTER}",
                options=stat_opts("sum"),
                field_config={"defaults": {"unit": "short"}, "overrides": []},
            ),
            panel(
                4,
                "Cache hits",
                "stat",
                18,
                0,
                6,
                4,
                f"SELECT count() FROM route_agent_observability.logs WHERE event = 'agent_cache_hit' AND {FILTER}",
                options=stat_opts(),
            ),
            panel(
                5,
                "Cost over time",
                "timeseries",
                0,
                4,
                12,
                8,
                f"SELECT toStartOfMinute(timestamp) AS time, sum(JSONExtractFloat(extra, 'cost_usd')) AS cost_usd FROM route_agent_observability.logs WHERE {FILTER} GROUP BY time ORDER BY time",
                timeseries=True,
                field_config={"defaults": {"unit": "currencyUSD"}, "overrides": []},
            ),
            panel(
                6,
                "Tokens over time",
                "timeseries",
                12,
                4,
                12,
                8,
                f"SELECT toStartOfMinute(timestamp) AS time, sum(JSONExtractInt(extra, 'prompt_tokens')) AS prompt, sum(JSONExtractInt(extra, 'completion_tokens')) AS completion FROM route_agent_observability.logs WHERE event = 'llm_generation' AND {FILTER} GROUP BY time ORDER BY time",
                timeseries=True,
            ),
            panel(
                7,
                "By model",
                "table",
                0,
                12,
                12,
                8,
                f"""
SELECT
  JSONExtractString(extra, 'model') AS model,
  count() AS generations,
  countIf(status = 'error') AS errors,
  sum(JSONExtractInt(extra, 'prompt_tokens')) AS prompt_tokens,
  sum(JSONExtractInt(extra, 'completion_tokens')) AS completion_tokens,
  sum(JSONExtractFloat(extra, 'cost_usd')) AS cost_usd,
  avg(duration_ms) AS avg_ms
FROM route_agent_observability.logs
WHERE event = 'llm_generation' AND {FILTER}
GROUP BY model
ORDER BY generations DESC
""".strip(),
            ),
            panel(
                8,
                "Agent cache",
                "table",
                12,
                12,
                12,
                8,
                f"""
SELECT
  countIf(event = 'agent_cache_hit') AS hits,
  countIf(event = 'agent_complete' AND JSONExtractBool(extra, 'cache_hit') = 0) AS misses,
  if(hits + misses = 0, 0, hits / (hits + misses)) AS hit_ratio
FROM route_agent_observability.logs
WHERE event IN ('agent_cache_hit','agent_complete') AND {FILTER}
""".strip(),
            ),
            panel(
                9,
                "Generation log",
                "table",
                0,
                20,
                24,
                10,
                f"""
SELECT
  timestamp,
  run_id,
  request_id,
  JSONExtractString(extra, 'model') AS model,
  JSONExtractInt(extra, 'attempt') AS attempt,
  JSONExtractInt(extra, 'prompt_tokens') AS prompt_tokens,
  JSONExtractInt(extra, 'completion_tokens') AS completion_tokens,
  JSONExtractFloat(extra, 'cost_usd') AS cost_usd,
  duration_ms,
  status,
  JSONExtractString(extra, 'error_type') AS error_type
FROM route_agent_observability.logs
WHERE event = 'llm_generation' AND {FILTER}
ORDER BY timestamp DESC
LIMIT 200
""".strip(),
            ),
        ],
    )


def explorer() -> dict[str, object]:
    return dashboard(
        uid="route-agent-explorer",
        title="Route Agent / Run Explorer",
        description="Paste a run_id, request_id, or job_id to reconstruct the timeline.",
        tags=["route-agent", "explorer"],
        panels=[
            panel(
                1,
                "Timeline",
                "table",
                0,
                0,
                24,
                16,
                f"""
SELECT
  timestamp,
  level,
  event,
  component,
  stage,
  status,
  duration_ms,
  message,
  run_id,
  request_id,
  job_id
FROM route_agent_observability.logs
WHERE {FILTER}
ORDER BY timestamp
LIMIT 500
""".strip(),
                description="Full correlated log stream for the selected ids.",
            ),
            panel(
                2,
                "Stage pairs",
                "table",
                0,
                16,
                12,
                8,
                f"""
SELECT
  timestamp,
  JSONExtractString(extra, 'kind') AS kind,
  stage,
  status,
  JSONExtractString(extra, 'detail') AS detail,
  run_id,
  request_id
FROM route_agent_observability.logs
WHERE event LIKE 'pipeline_event_%' AND {FILTER}
ORDER BY timestamp
LIMIT 200
""".strip(),
            ),
            panel(
                3,
                "HTTP / jobs",
                "table",
                12,
                16,
                12,
                8,
                f"""
SELECT
  timestamp,
  event,
  JSONExtractString(extra, 'method') AS method,
  JSONExtractString(extra, 'path') AS path,
  JSONExtractInt(extra, 'status_code') AS status_code,
  duration_ms,
  run_id,
  job_id,
  request_id
FROM route_agent_observability.logs
WHERE event IN ('http_request','http_response','job_queued','job_running','job_completed','job_failed')
  AND {FILTER}
ORDER BY timestamp DESC
LIMIT 100
""".strip(),
            ),
        ],
    )


def main() -> None:
    out = Path(__file__).parent
    files = {
        "route-agent.json": overview(),
        "pipeline.json": pipeline(),
        "errors.json": errors(),
        "llm.json": llm(),
        "explorer.json": explorer(),
    }
    for name, payload in files.items():
        path = out / name
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(path.name)


if __name__ == "__main__":
    main()
