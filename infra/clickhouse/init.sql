CREATE DATABASE IF NOT EXISTS route_agent_observability;

CREATE TABLE IF NOT EXISTS route_agent_observability.logs
(
    timestamp DateTime64(3, 'UTC'),
    level LowCardinality(String),
    logger String,
    message String,
    event String,
    component String,
    source LowCardinality(Nullable(String)),
    run_id Nullable(String),
    request_id Nullable(String),
    job_id Nullable(String),
    command Nullable(String),
    stage Nullable(String),
    duration_ms Nullable(Float64),
    status Nullable(String),
    extra String DEFAULT '{}'
)
ENGINE = MergeTree
PARTITION BY toDate(timestamp)
ORDER BY (timestamp, event, cityHash64(ifNull(run_id, ''), ifNull(request_id, '')))
TTL toDateTime(timestamp) + INTERVAL 14 DAY
SETTINGS index_granularity = 8192;

CREATE VIEW IF NOT EXISTS route_agent_observability.runs AS
SELECT
    run_id,
    any(request_id) AS request_id,
    any(job_id) AS job_id,
    any(source) AS source,
    min(timestamp) AS started_at,
    max(timestamp) AS finished_at,
    count() AS log_count,
    countIf(level IN ('ERROR', 'CRITICAL')) AS error_count
FROM route_agent_observability.logs
WHERE run_id IS NOT NULL
GROUP BY run_id;

CREATE VIEW IF NOT EXISTS route_agent_observability.errors AS
SELECT
    timestamp,
    run_id,
    request_id,
    job_id,
    component,
    event,
    message,
    status
FROM route_agent_observability.logs
WHERE level IN ('ERROR', 'CRITICAL');

CREATE VIEW IF NOT EXISTS route_agent_observability.stage_latency AS
SELECT
    event,
    stage,
    run_id,
    request_id,
    duration_ms,
    timestamp
FROM route_agent_observability.logs
WHERE duration_ms IS NOT NULL;

CREATE VIEW IF NOT EXISTS route_agent_observability.llm_cost AS
SELECT
    timestamp,
    run_id,
    request_id,
    job_id,
    event,
    JSONExtractFloat(extra, 'cost_usd') AS cost_usd,
    JSONExtractInt(extra, 'prompt_tokens') AS prompt_tokens,
    JSONExtractInt(extra, 'completion_tokens') AS completion_tokens,
    JSONExtractInt(extra, 'calls') AS calls
FROM route_agent_observability.logs
WHERE JSONHas(extra, 'cost_usd') OR JSONHas(extra, 'prompt_tokens');
