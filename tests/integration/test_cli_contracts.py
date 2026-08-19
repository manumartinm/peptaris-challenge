from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.support.cli import CliCase
from tests.support.score import validate_schema


class TestCliContracts(CliCase):
    @pytest.mark.parametrize("command", ["validate", "walk", "run"])
    def test_missing_request_file_exits_one(self, tmp_path: Path, command: str) -> None:
        result = self.invoke(command, str(tmp_path / "missing.json"), "--no-model")
        assert result.exit_code == 1
        assert "request file not found" in result.stderr

    @pytest.mark.parametrize(
        ("command", "exit_code"),
        [("validate", 2), ("walk", 2), ("run", 0)],
    )
    def test_invalid_site_uses_command_exit_contract(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        command: str,
        exit_code: int,
    ) -> None:
        monkeypatch.setenv("ROUTE_AGENT_MOLECULAR_SKIP_3D", "true")
        request_path = self.write_json(
            tmp_path,
            self.payload(
                request_id="T-SITE",
                sequence="ACDE",
                modifications=[{"family": "lipidation", "site": "K12"}],
            ),
        )
        args = [command, str(request_path), "--no-model"]
        if command == "run":
            args.extend(["--trace-dir", str(tmp_path / "traces")])
        result = self.invoke(*args)
        assert result.exit_code == exit_code, result.stdout + result.stderr
        payload = json.loads(result.stdout)
        if command == "validate":
            assert payload["conflicts"][0]["kind"] == "site_invalid"
        elif command == "walk":
            assert payload["surviving_ids"] == []
            assert payload["nodes"][0]["state"]["status"] == "fail"
        else:
            assert payload["verdict"] in {"infeasible", "insufficient_information"}
            assert any(item["kind"] == "site_invalid" for item in payload["conflicts"])
            schema = validate_schema(payload, tmp_path)
            assert schema["invalid"] == []
