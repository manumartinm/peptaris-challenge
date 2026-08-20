from __future__ import annotations

from pathlib import Path

import pytest

from tests.support.cli import PUBLIC_VERDICT_FIELDS, CliCase, load_jsonl
from tests.support.score import write_eval_pair


class TestCliEval(CliCase):
    def test_eval_writes_actual_jsonl_and_report(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ROUTE_AGENT_MOLECULAR_SKIP_3D", "true")
        requests, expected = write_eval_pair(
            tmp_path,
            [self.amide_acetylation_payload("T-EVAL")],
            [
                {
                    "request_id": "T-EVAL",
                    "verdict": ["insufficient_information", "feasible"],
                    "conflicts": [],
                    "clean": True,
                }
            ],
        )
        actual = tmp_path / "actual.jsonl"
        report = tmp_path / "EVAL_REPORT.md"
        traces = tmp_path / "traces"
        result = self.invoke(
            "eval",
            str(requests),
            "--expected",
            str(expected),
            "--output",
            str(actual),
            "--report",
            str(report),
            "--trace-dir",
            str(traces),
            "--no-model",
        )
        assert result.exit_code == 0, result.stdout + result.stderr
        rows = load_jsonl(actual)
        assert len(rows) == 1
        assert set(rows[0]) == PUBLIC_VERDICT_FIELDS
        markdown = report.read_text(encoding="utf-8")
        assert "T-EVAL" in markdown or "score.py" in markdown
        assert "scramble" in markdown.lower()
        assert (traces / "T-EVAL.trace.json").is_file()

    def test_eval_strict_exits_nonzero_on_invalid_schema(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ROUTE_AGENT_MOLECULAR_SKIP_3D", "true")
        requests, expected = write_eval_pair(
            tmp_path,
            [self.amide_acetylation_payload("T-EVAL")],
            [
                {
                    "request_id": "T-EVAL",
                    "verdict": "feasible",
                    "conflicts": [],
                    "clean": True,
                    "forbidden_kinds": ["site_invalid"],
                    "alternates": [{"forbidden_kinds": []}],
                }
            ],
        )
        result = self.invoke(
            "eval",
            str(requests),
            "--expected",
            str(expected),
            "--output",
            str(tmp_path / "actual.jsonl"),
            "--report",
            str(tmp_path / "EVAL_REPORT.md"),
            "--trace-dir",
            str(tmp_path / "traces"),
            "--no-model",
            "--strict",
        )
        assert result.exit_code == 2, result.stdout + result.stderr

    def test_eval_without_expected_launches_without_scoring(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ROUTE_AGENT_MOLECULAR_SKIP_3D", "true")
        requests, _expected = write_eval_pair(
            tmp_path,
            [self.amide_acetylation_payload("T-LAUNCH")],
            [],
        )
        actual = tmp_path / "actual.jsonl"
        report = tmp_path / "EVAL_REPORT.md"
        traces = tmp_path / "traces"
        result = self.invoke(
            "eval",
            str(requests),
            "--output",
            str(actual),
            "--report",
            str(report),
            "--trace-dir",
            str(traces),
            "--no-model",
        )
        assert result.exit_code == 0, result.stdout + result.stderr
        rows = load_jsonl(actual)
        assert len(rows) == 1
        assert rows[0]["request_id"] == "T-LAUNCH"
        assert set(rows[0]) == PUBLIC_VERDICT_FIELDS
        assert (traces / "T-LAUNCH.trace.json").is_file()
        assert not report.exists()
