from __future__ import annotations

import json
import statistics
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from route_agent.models.agent import CostBreakdown
from route_agent.models.request import DesignRequest
from route_agent.observability import StructuredLogger, bind_context
from route_agent.pipeline import RunResult
from route_agent.trace import TraceWriter


class PipelineLike(Protocol):
    def run(self, request: DesignRequest) -> RunResult: ...


@dataclass(frozen=True)
class EvalSummary:
    cases: int
    score: dict[str, Any]
    schema: dict[str, Any]
    actual_path: Path
    report_path: Path
    key_problems: tuple[str, ...] = ()


class DevEvaluator:
    def __init__(
        self,
        pipeline: PipelineLike,
        score_py: Path,
        schema_json: Path,
        logger: StructuredLogger | None = None,
    ) -> None:
        self._pipeline = pipeline
        self._score_py = score_py
        self._schema_json = schema_json
        self._logger = logger or StructuredLogger("route_agent.eval")

    def run(
        self,
        *,
        requests_path: Path,
        expected_path: Path,
        actual_path: Path,
        report_path: Path,
        trace_dir: Path,
    ) -> EvalSummary:
        requests = load_design_requests(requests_path)
        key_check = self._validate_key(expected_path)
        problems = tuple(key_check.get("problems") or ())
        structural = _structural_key_problems(problems)
        if structural:
            raise ValueError("expected key is invalid: " + "; ".join(structural))
        writer = TraceWriter(trace_dir)
        actuals: list[dict[str, Any]] = []
        costs: list[tuple[str, CostBreakdown]] = []
        for request in requests:
            self._logger.info("eval_case_start", request_id=request.request_id)
            with bind_context(request_id=request.request_id):
                result = self._pipeline.run(request)
            if result.trace_path is None:
                writer.write(result.trace)
            actuals.append(result.verdict.model_dump(mode="json"))
            costs.append((request.request_id, result.cost.total))
        write_jsonl(actual_path, actuals)
        schema = self._validate_schema(actual_path)
        score = self._score(expected_path, actual_path)
        report_path.write_text(
            render_eval_report(score=score, schema=schema, costs=costs),
            encoding="utf-8",
        )
        self._logger.info(
            "eval_complete",
            cases=len(requests),
            points=score.get("points"),
            score=score.get("score"),
            actual=str(actual_path),
            report=str(report_path),
        )
        return EvalSummary(
            cases=len(requests),
            score=score,
            schema=schema,
            actual_path=actual_path,
            report_path=report_path,
            key_problems=problems,
        )

    def _validate_schema(self, actual_path: Path) -> dict[str, Any]:
        completed = subprocess.run(
            [
                sys.executable,
                str(self._score_py),
                "--validate",
                str(actual_path),
                str(self._schema_json),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode not in {0, 1}:
            raise RuntimeError(completed.stderr or "score.py --validate failed")
        return cast(dict[str, Any], json.loads(completed.stdout))

    def _validate_key(self, expected_path: Path) -> dict[str, Any]:
        completed = subprocess.run(
            [
                sys.executable,
                str(self._score_py),
                "--validate-key",
                str(expected_path),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode not in {0, 1}:
            raise RuntimeError(completed.stderr or "score.py --validate-key failed")
        if not completed.stdout.strip():
            return {"problems": []}
        return cast(dict[str, Any], json.loads(completed.stdout))

    def _score(self, expected_path: Path, actual_path: Path) -> dict[str, Any]:
        completed = subprocess.run(
            [
                sys.executable,
                str(self._score_py),
                str(expected_path),
                str(actual_path),
                "--json",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr or "score.py scoring failed")
        return cast(dict[str, Any], json.loads(completed.stdout))


def _structural_key_problems(problems: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(item for item in problems if not item.startswith("a constant"))


def load_design_requests(path: Path) -> list[DesignRequest]:
    rows: list[DesignRequest] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no}: invalid JSON ({exc})") from exc
        rows.append(DesignRequest.model_validate(payload))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )


def render_eval_report(
    *,
    score: dict[str, Any],
    schema: dict[str, Any],
    costs: list[tuple[str, CostBreakdown]],
) -> str:
    points = score.get("points")
    max_points = score.get("max_points")
    headline = f"{points}/{max_points} ({score.get('score')})"
    failures = [
        case
        for case in score.get("per_case", [])
        if isinstance(case, dict) and int(case.get("points", 0)) < 2
    ]
    invalid = schema.get("invalid") or []
    lines = [
        "# EVAL_REPORT",
        "",
        "Official `data/score.py` against the provided expected key (dev set only).",
        "",
        f"**Headline:** {headline}",
        "",
        *_zero_call_note(costs),
        "## Official metrics",
        "",
        f"- `site_map_exact`: {_fmt_metric(score.get('site_map_exact'))}",
        (
            "- `resolved_sequence_exact`: "
            f"{_fmt_metric(score.get('resolved_sequence_exact'))}"
        ),
        (
            "- `negative_control_recall`: "
            f"{_fmt_metric(score.get('negative_control_recall'))}"
        ),
        f"- `conflict_recall`: {_fmt_metric(score.get('conflict_recall'))}",
        f"- `clean_case_precision`: {_fmt_metric(score.get('clean_case_precision'))}",
        "",
        "## Model calls and tokens",
        "",
        *_cost_lines(costs),
        "",
        "## Schema validation",
        "",
        (
            f"`score.py --validate` checked {schema.get('checked')} "
            f"with {len(invalid)} invalid object(s)."
        ),
        "",
        "## Where this agent fails",
        "",
        *_failure_lines(failures, invalid),
        "",
        "## Scope limits",
        "",
        "Self-authored expected key, scramble control, and ablations "
        "(including no-model ablation as a scored comparison) were **not run**. "
        "No numbers are invented for those controls.",
        "",
        "This report covers only `design_requests.jsonl` vs `expected_dev.jsonl` "
        "when those files are passed to `route-agent eval`.",
        "",
    ]
    return "\n".join(lines)


def _fmt_metric(value: object) -> str:
    if value is None:
        return "n/a"
    return str(value)


def _zero_call_note(costs: list[tuple[str, CostBreakdown]]) -> list[str]:
    if costs and all(item.calls == 0 for _, item in costs):
        return [
            "This run recorded **zero model calls** (offline / `--no-model`).",
            "",
        ]
    return []


def _cost_lines(costs: list[tuple[str, CostBreakdown]]) -> list[str]:
    if not costs:
        return ["No LLM call records were collected."]
    calls = [item.calls for _, item in costs]
    tokens = [item.input_tokens + item.output_tokens for _, item in costs]
    worst_calls = max(costs, key=lambda item: item[1].calls)
    worst_tokens = max(
        costs, key=lambda item: item[1].input_tokens + item[1].output_tokens
    )
    return [
        f"- median calls: {statistics.median(calls)}",
        f"- worst calls: {worst_calls[1].calls} (`{worst_calls[0]}`)",
        f"- median tokens (in+out): {statistics.median(tokens)}",
        f"- worst tokens (in+out): "
        f"{worst_tokens[1].input_tokens + worst_tokens[1].output_tokens} "
        f"(`{worst_tokens[0]}`)",
    ]


def _failure_lines(
    failures: list[dict[str, Any]], invalid: list[dict[str, Any]]
) -> list[str]:
    if not failures and not invalid:
        return ["No case scored below 2/2 and no schema failures."]
    lines: list[str] = []
    for case in failures:
        extra = case.get("unexpected_kinds") or []
        suffix = f" unexpected={extra}" if extra else ""
        lines.append(
            f"- `{case.get('request_id')}`: {case.get('points')}/2 "
            f"{case.get('reason')}{suffix}"
        )
    for item in invalid:
        lines.append(
            f"- schema `{item.get('request_id')}` line {item.get('line')}: "
            f"{item.get('error')}"
        )
    return lines
