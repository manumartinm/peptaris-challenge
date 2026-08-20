from __future__ import annotations

from pathlib import Path

import pytest

from route_agent.evaluation import DevEvaluator, render_eval_report
from route_agent.models.agent import CostBreakdown, CostReport
from route_agent.models.request import DesignRequest
from route_agent.models.trace import PipelineTrace
from route_agent.models.verdict import RouteVerdict
from route_agent.pipeline import RunResult
from tests.support.conflict_fixtures import (
    empty_validation,
    make_tree,
    post_graph_report,
)
from tests.support.score import SCHEMA_JSON, SCORE_PY, write_eval_pair
from tests.support.validation_case import ValidationCase


def _verdict(request_id: str, verdict: str = "infeasible") -> RouteVerdict:
    validation = empty_validation(request_id)
    return RouteVerdict(
        request_id=request_id,
        verdict=verdict,  # type: ignore[arg-type]
        confidence="low",
        resolved_sequence="ACDE",
        resolved_annotations={},
        site_map=validation.site_map,
        route=(),
        conflicts=(),
        unknowns=("scripted",),
    )


def _run_result(request: DesignRequest) -> RunResult:
    verdict = _verdict(request.request_id)
    validation = empty_validation(request.request_id)
    tree = make_tree([], [], surviving_ids=())
    cost = CostReport(
        total=CostBreakdown(cost_usd=0.0, input_tokens=12, output_tokens=4, calls=2)
    )
    trace = PipelineTrace(
        request_id=request.request_id,
        request=request,
        validation=validation,
        tree=tree.to_report(request.request_id),
        post_graph=post_graph_report(request.request_id, selected_id=None),
        judge=None,
        verdict=verdict,
        cost=cost,
    )
    return RunResult(verdict=verdict, cost=cost, trace=trace)


class ScriptedPipeline:
    def __init__(self) -> None:
        self.ids: list[str] = []

    def run(self, request: DesignRequest) -> RunResult:
        self.ids.append(request.request_id)
        return _run_result(request)


class TestRenderEvalReport:
    def test_declares_skipped_controls_and_includes_score_metrics(self) -> None:
        markdown = render_eval_report(
            score={
                "cases": 2,
                "points": 2,
                "max_points": 4,
                "score": 0.5,
                "site_map_exact": 1.0,
                "resolved_sequence_exact": 0.5,
                "negative_control_recall": 1.0,
                "per_case": [
                    {
                        "request_id": "T-OK",
                        "points": 2,
                        "reason": "ok",
                        "unexpected_kinds": [],
                    },
                    {
                        "request_id": "T-FAIL",
                        "points": 0,
                        "reason": "wrong_verdict",
                        "unexpected_kinds": ["site_invalid"],
                    },
                ],
            },
            schema={"checked": True, "invalid": []},
            costs=[
                ("T-OK", CostBreakdown(calls=2, input_tokens=10, output_tokens=5)),
                ("T-FAIL", CostBreakdown(calls=4, input_tokens=20, output_tokens=9)),
            ],
        )
        assert "2/4" in markdown
        assert "site_map_exact" in markdown
        assert "resolved_sequence_exact" in markdown
        assert "negative_control_recall" in markdown
        assert "T-FAIL" in markdown
        assert "wrong_verdict" in markdown
        assert "self-authored" in markdown.lower() or "self-written" in markdown.lower()
        assert "scramble" in markdown.lower()
        assert "ablation" in markdown.lower()
        assert "not run" in markdown.lower() or "not executed" in markdown.lower()
        assert "median" in markdown.lower()
        assert "worst" in markdown.lower()
        zero = render_eval_report(
            score={
                "cases": 1,
                "points": 0,
                "max_points": 2,
                "score": 0.0,
                "site_map_exact": None,
                "resolved_sequence_exact": None,
                "negative_control_recall": None,
                "per_case": [
                    {
                        "request_id": "T-OFF",
                        "points": 0,
                        "reason": "miss",
                        "unexpected_kinds": [],
                    }
                ],
            },
            schema={"checked": True, "invalid": []},
            costs=[("T-OFF", CostBreakdown(calls=0, input_tokens=0, output_tokens=0))],
        )
        assert "zero model calls" in zero.lower()


class TestDevEvaluator(ValidationCase):
    def test_writes_jsonl_traces_and_report(self, tmp_path: Path) -> None:
        requests, expected = write_eval_pair(
            tmp_path,
            [
                self.payload(request_id="T-OK", sequence="ACDE"),
                self.payload(request_id="T-FAIL", sequence="ACDE"),
            ],
            [
                {
                    "request_id": "T-OK",
                    "verdict": "infeasible",
                    "conflicts": [],
                    "clean": True,
                },
                {
                    "request_id": "T-FAIL",
                    "verdict": "feasible",
                    "conflicts": [],
                    "clean": True,
                },
            ],
        )
        actual = tmp_path / "actual.jsonl"
        report = tmp_path / "EVAL_REPORT.md"
        traces = tmp_path / "traces"
        pipeline = ScriptedPipeline()
        summary = DevEvaluator(
            pipeline,
            score_py=SCORE_PY,
            schema_json=SCHEMA_JSON,
        ).run(
            requests_path=requests,
            expected_path=expected,
            actual_path=actual,
            report_path=report,
            trace_dir=traces,
        )
        assert pipeline.ids == ["T-OK", "T-FAIL"]
        lines = [
            line
            for line in actual.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(lines) == 2
        assert (traces / "T-OK.trace.json").is_file()
        assert (traces / "T-FAIL.trace.json").is_file()
        markdown = report.read_text(encoding="utf-8")
        assert "T-FAIL" in markdown
        assert "scramble" in markdown.lower()
        assert summary.cases == 2
        assert summary.score is not None
        assert summary.score["points"] == 2
        assert not any(item.startswith("T-") for item in summary.key_problems)

    def test_rejects_expected_key_with_problems(self, tmp_path: Path) -> None:
        requests, expected = write_eval_pair(
            tmp_path,
            [self.payload(request_id="T-OK", sequence="ACDE")],
            [
                {
                    "request_id": "T-OK",
                    "verdict": "feasible",
                    "conflicts": [],
                    "clean": True,
                    "forbidden_kinds": ["site_invalid"],
                    "alternates": [{"forbidden_kinds": []}],
                }
            ],
        )
        evaluator = DevEvaluator(
            ScriptedPipeline(),
            score_py=SCORE_PY,
            schema_json=SCHEMA_JSON,
        )
        with pytest.raises(ValueError, match="expected key"):
            evaluator.run(
                requests_path=requests,
                expected_path=expected,
                actual_path=tmp_path / "actual.jsonl",
                report_path=tmp_path / "EVAL_REPORT.md",
                trace_dir=tmp_path / "traces",
            )

    def test_launches_without_expected_and_skips_score(self, tmp_path: Path) -> None:
        requests, _expected = write_eval_pair(
            tmp_path,
            [
                self.payload(request_id="T-A", sequence="ACDE"),
                self.payload(request_id="T-B", sequence="ACDE"),
            ],
            [],
        )
        actual = tmp_path / "actual.jsonl"
        report = tmp_path / "EVAL_REPORT.md"
        traces = tmp_path / "traces"
        pipeline = ScriptedPipeline()
        summary = DevEvaluator(
            pipeline,
            score_py=tmp_path / "missing-score.py",
            schema_json=tmp_path / "missing-schema.json",
        ).run(
            requests_path=requests,
            expected_path=None,
            actual_path=actual,
            report_path=report,
            trace_dir=traces,
        )
        assert pipeline.ids == ["T-A", "T-B"]
        lines = [
            line
            for line in actual.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(lines) == 2
        assert (traces / "T-A.trace.json").is_file()
        assert (traces / "T-B.trace.json").is_file()
        assert not report.exists()
        assert summary.cases == 2
        assert summary.score is None
        assert summary.schema == {}
        assert summary.key_problems == ()
