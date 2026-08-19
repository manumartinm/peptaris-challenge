from __future__ import annotations

import json
from pathlib import Path

from tests.support.cli import CliCase


class TestCliAgent(CliCase):
    def test_agent_no_model_writes_result_without_verdict(self, tmp_path: Path) -> None:
        request_path = self.write_json(tmp_path, self.design_request_row("REQ-01"))
        output = tmp_path / "out.json"

        result = self.invoke(
            "agent",
            str(request_path),
            "--objective",
            "check_compatibility",
            "--no-model",
            "--output",
            str(output),
        )

        assert result.exit_code == 0, result.stdout + result.stderr
        payload = json.loads(output.read_text(encoding="utf-8"))
        assert payload["objective"] == "check_compatibility"
        assert "verdict" not in payload
        assert payload["passed"] is None
        assert payload["unknowns"]
        assert "sk-" not in result.stdout
        assert "sk-" not in result.stderr

    def test_agent_missing_state_file_exits_one(self, tmp_path: Path) -> None:
        request_path = self.write_json(tmp_path, self.design_request_row("REQ-01"))
        result = self.invoke(
            "agent",
            str(request_path),
            "--state",
            str(tmp_path / "missing.json"),
            "--no-model",
        )
        assert result.exit_code == 1
        assert "state file not found" in result.stderr

    def test_agent_malformed_state_json_exits_one(self, tmp_path: Path) -> None:
        request_path = self.write_json(tmp_path, self.design_request_row("REQ-01"))
        state_path = self.write_json(tmp_path, "{not json", "state.json")
        result = self.invoke(
            "agent", str(request_path), "--state", str(state_path), "--no-model"
        )
        assert result.exit_code == 1
        assert "JSON" in result.stderr or "json" in result.stderr.lower()
