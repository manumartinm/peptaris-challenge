from __future__ import annotations

import json
from pathlib import Path

from click.testing import Result

from tests.support.cli import CliCase
from tests.support.validation_case import GLUCAGON


class TestCliValidate(CliCase):
    def invoke_validate(self, *args: str) -> Result:
        return self.invoke("validate", *args, "--no-model")

    def test_validate_req05_writes_state0_json(self, tmp_path: Path) -> None:
        request_path = self.write_json(
            tmp_path, self.design_request_row("REQ-05"), "req05.json"
        )
        output = tmp_path / "out.json"

        result = self.invoke_validate(str(request_path), "--output", str(output))

        assert result.exit_code == 0, result.stdout + result.stderr
        payload = json.loads(output.read_text(encoding="utf-8"))
        assert payload["request_id"] == "REQ-05"
        assert payload["state"]["id"] == "state_0"
        assert payload["site_map"][0]["requested"] == "K5"
        assert payload["resolved_sequence"] == "FCFWKTCX"
        assert "sk-" not in result.stdout
        assert "sk-" not in result.stderr

    def test_validate_missing_detail_is_accepted(self, tmp_path: Path) -> None:
        request_path = self.write_json(
            tmp_path,
            self.payload(
                request_id="T-CLI",
                parent_name="glucagon",
                sequence=GLUCAGON,
                modifications=[{"family": "lipidation", "site": "K12"}],
            ),
        )

        result = self.invoke_validate(str(request_path))

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["state"]["status"] == "pass"

    def test_validate_malformed_json_exits_one(self, tmp_path: Path) -> None:
        request_path = self.write_json(tmp_path, "{not json", "bad.json")

        result = self.invoke_validate(str(request_path))

        assert result.exit_code == 1
        assert "JSON" in result.stderr or "json" in result.stderr.lower()

    def test_default_logs_hide_progress_on_stderr(self, tmp_path: Path) -> None:
        request_path = self.write_json(tmp_path, self.design_request_row("REQ-09"))

        result = self.invoke_validate(str(request_path))

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["request_id"] == "REQ-09"
        assert "INFO" not in result.stderr
        assert "validation_complete" not in result.stderr
        assert "validation_stage" not in result.stderr

    def test_verbose_shows_progress_info_logs(self, tmp_path: Path) -> None:
        request_path = self.write_json(tmp_path, self.design_request_row("REQ-09"))

        result = self.invoke("validate", str(request_path), "--no-model", "-v")

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["request_id"] == "REQ-09"
        assert "INFO" in result.stderr
        assert "validation_complete" in result.stderr
        assert "validation_stage" not in result.stderr

    def test_very_verbose_enables_debug_stage_logs(self, tmp_path: Path) -> None:
        request_path = self.write_json(tmp_path, self.design_request_row("REQ-09"))

        result = self.invoke("validate", str(request_path), "--no-model", "-vv")

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["request_id"] == "REQ-09"
        assert "DEBUG" in result.stderr
        assert "validation_stage" in result.stderr

    def test_json_log_format_keeps_stdout_parseable(self, tmp_path: Path) -> None:
        request_path = self.write_json(tmp_path, self.design_request_row("REQ-09"))

        result = self.invoke(
            "validate",
            str(request_path),
            "--no-model",
            "-v",
            "--log-format",
            "json",
        )

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["request_id"] == "REQ-09"
        records = [
            json.loads(line)
            for line in result.stderr.splitlines()
            if line.startswith("{")
        ]
        assert records
        assert any(record["message"] == "validation_complete" for record in records)
        assert all("timestamp" in record and "level" in record for record in records)
