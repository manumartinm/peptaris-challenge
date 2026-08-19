from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from route_agent.doctor import run_doctor
from route_agent.settings import Settings
from route_agent_cli.app import app


class TestDoctor:
    runner = CliRunner()

    def test_doctor_no_model_exits_zero_without_key(self) -> None:
        result = self.runner.invoke(app, ["doctor", "--no-model"])
        assert result.exit_code == 0, result.output + result.stderr
        assert "python" in result.output
        assert "rdkit" in result.output
        assert "api_key" in result.output

    def test_doctor_json_is_stable(self) -> None:
        result = self.runner.invoke(
            app, ["doctor", "--no-model", "--log-format", "json"]
        )
        assert result.exit_code == 0, result.output + result.stderr
        payload = json.loads(result.output)
        assert payload["ok"] is True
        names = {item["name"] for item in payload["checks"]}
        assert {"python", "resources", "rdkit", "api_key"} <= names

    def test_doctor_service_marks_missing_key_as_fail(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setattr("route_agent.doctor.credential_status", _absent)
        report = run_doctor(Settings(no_model=False), no_model=False)
        api_key = next(item for item in report.checks if item.name == "api_key")
        assert api_key.status == "fail"
        assert report.failed is True


def _absent(provider: str, *, env_value: str | None) -> object:
    from route_agent.credentials import CredentialStatus

    return CredentialStatus(
        provider="anthropic", in_environment=False, in_keyring=False
    )
