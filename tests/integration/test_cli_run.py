from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.support.cli import PUBLIC_VERDICT_FIELDS, VERDICTS, CliCase
from tests.support.score import validate_schema


class TestCliRun(CliCase):
    def test_run_writes_schema_exact_verdict_and_trace(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ROUTE_AGENT_MOLECULAR_SKIP_3D", "true")
        request_path = self.write_json(
            tmp_path, self.amide_acetylation_payload("T-RUN")
        )
        output = tmp_path / "out.json"
        traces = tmp_path / "traces"
        result = self.invoke(
            "run",
            str(request_path),
            "--no-model",
            "--output",
            str(output),
            "--trace-dir",
            str(traces),
        )
        assert result.exit_code == 0, result.stdout + result.stderr
        payload = json.loads(output.read_text(encoding="utf-8"))
        assert set(payload) == PUBLIC_VERDICT_FIELDS
        assert payload["request_id"] == "T-RUN"
        assert payload["verdict"] in VERDICTS
        assert payload["confidence"] == "low"
        assert payload["unknowns"] != ["model disabled"]
        schema = validate_schema(payload, tmp_path)
        assert schema["invalid"] == []
        assert (traces / "T-RUN.trace.json").is_file()

    def test_run_accepts_model_and_reasoning(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ROUTE_AGENT_MOLECULAR_SKIP_3D", "true")
        request_path = self.write_json(
            tmp_path, self.amide_acetylation_payload("T-RUN-MODEL")
        )
        result = self.invoke(
            "run",
            str(request_path),
            "--no-model",
            "--model",
            "openai/gpt-5.6-terra",
            "--reasoning",
            "high",
            "--trace-dir",
            str(tmp_path / "traces"),
            "-v",
        )
        assert result.exit_code == 0, result.stdout + result.stderr
        payload = json.loads(result.stdout)
        assert payload["request_id"] == "T-RUN-MODEL"
        assert payload["verdict"] in VERDICTS
        assert "openai/gpt-5.6-terra" in result.stderr
        assert "high" in result.stderr

    def test_run_rejects_unknown_reasoning(self, tmp_path: Path) -> None:
        result = self.invoke(
            "run",
            str(tmp_path / "req.json"),
            "--no-model",
            "--reasoning",
            "extreme",
        )
        assert result.exit_code != 0
        assert "reasoning" in result.output.lower() or "extreme" in result.output
