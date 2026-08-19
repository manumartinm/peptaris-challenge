from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.support.cli import PUBLIC_VERDICT_FIELDS, CliCase, load_jsonl
from tests.support.score import validate_jsonl
from tests.support.validation_case import DATA_DIR

OFFICIAL_REQUESTS = DATA_DIR / "design_requests.jsonl"
OFFICIAL_EXPECTED = DATA_DIR / "expected_dev.jsonl"


@pytest.mark.eval
class TestOfficialEval(CliCase):
    def test_offline_dev_set_writes_schema_valid_outputs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ROUTE_AGENT_MOLECULAR_SKIP_3D", "true")
        root = Path(os.environ.get("ROUTE_AGENT_EVAL_OUTPUT", str(tmp_path)))
        root.mkdir(parents=True, exist_ok=True)
        actual = root / "actual.jsonl"
        report = root / "EVAL_REPORT.md"
        traces = root / "traces"
        expected_ids = [
            row["request_id"]
            for row in load_jsonl(OFFICIAL_REQUESTS)
            if "request_id" in row
        ]
        assert len(expected_ids) == 12
        result = self.invoke(
            "debug",
            "eval",
            str(OFFICIAL_REQUESTS),
            "--expected",
            str(OFFICIAL_EXPECTED),
            "--output",
            str(actual),
            "--report",
            str(report),
            "--trace-dir",
            str(traces),
            "--no-model",
            "--strict",
        )
        assert result.exit_code == 0, result.stdout + result.stderr
        rows = load_jsonl(actual)
        assert [row["request_id"] for row in rows] == expected_ids
        for row in rows:
            assert set(row) == PUBLIC_VERDICT_FIELDS
        schema = validate_jsonl(actual)
        assert schema.get("invalid") == []
        markdown = report.read_text(encoding="utf-8")
        assert "EVAL_REPORT" in markdown
        assert "score.py" in markdown
        for request_id in expected_ids:
            assert (traces / f"{request_id}.trace.json").is_file()
