from __future__ import annotations

import pytest
from click.testing import CliRunner

from route_agent.credentials import (
    credential_status,
    get_api_key,
    set_api_key,
    unset_api_key,
)
from route_agent.settings import Settings
from route_agent_cli.app import app


class MemoryKeyring:
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def set_password(self, service: str, username: str, password: str) -> None:
        self._store[(service, username)] = password

    def get_password(self, service: str, username: str) -> str | None:
        return self._store.get((service, username))

    def delete_password(self, service: str, username: str) -> None:
        self._store.pop((service, username), None)


class TestCredentials:
    def test_keyring_round_trip(self, monkeypatch: pytest.MonkeyPatch) -> None:
        backend = MemoryKeyring()
        monkeypatch.setattr("keyring.set_password", backend.set_password)
        monkeypatch.setattr("keyring.get_password", backend.get_password)
        monkeypatch.setattr("keyring.delete_password", backend.delete_password)
        set_api_key("openai", "sk-test-openai")
        assert get_api_key("openai") == "sk-test-openai"
        assert unset_api_key("openai") is True
        assert get_api_key("openai") is None

    def test_env_beats_keyring(self, monkeypatch: pytest.MonkeyPatch) -> None:
        backend = MemoryKeyring()
        monkeypatch.setattr("keyring.set_password", backend.set_password)
        monkeypatch.setattr("keyring.get_password", backend.get_password)
        set_api_key("anthropic", "sk-from-keyring")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-from-env")
        monkeypatch.setenv("ROUTE_AGENT_MODEL", "anthropic/claude-sonnet-4-5")
        settings = Settings()
        assert settings.provider_api_key() == "sk-from-env"
        status = credential_status("anthropic", env_value="sk-from-env")
        assert status.source == "environment"

    def test_config_show_does_not_print_secrets(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        backend = MemoryKeyring()
        monkeypatch.setattr("keyring.set_password", backend.set_password)
        monkeypatch.setattr("keyring.get_password", backend.get_password)
        monkeypatch.setattr("keyring.delete_password", backend.delete_password)
        set_api_key("openai", "sk-secret-value")
        result = CliRunner().invoke(app, ["config", "show"])
        assert result.exit_code == 0
        assert "sk-secret-value" not in result.output
        assert "sk-secret-value" not in result.stderr
