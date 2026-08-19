from __future__ import annotations

import pytest

from route_agent.settings import (
    Settings,
    langchain_model_spec,
    uses_gpt5_reasoning_model,
    uses_openai_model,
)
from route_agent_cli.settings import settings_from_cli


class TestLangchainModelSpec:
    def test_converts_litellm_slash_to_langchain_colon(self) -> None:
        assert langchain_model_spec("openai/gpt-4o-mini") == "openai:gpt-4o-mini"
        assert (
            langchain_model_spec("anthropic/claude-sonnet-4-5")
            == "anthropic:claude-sonnet-4-5"
        )
        assert uses_openai_model("openai/gpt-4o-mini") is True
        assert uses_openai_model("anthropic/claude-sonnet-4-5") is False

    def test_leaves_langchain_and_bare_names_unchanged(self) -> None:
        assert langchain_model_spec("openai:gpt-4o-mini") == "openai:gpt-4o-mini"
        assert langchain_model_spec("gpt-4o-mini") == "gpt-4o-mini"

    def test_detects_gpt5_reasoning_models(self) -> None:
        assert uses_gpt5_reasoning_model("openai/gpt-5.6-terra") is True
        assert uses_gpt5_reasoning_model("openai:gpt-5.4") is True
        assert uses_gpt5_reasoning_model("openai/gpt-5-chat-latest") is False
        assert uses_gpt5_reasoning_model("openai/gpt-4o-mini") is False
        assert uses_gpt5_reasoning_model("anthropic/claude-sonnet-4-5") is False


class TestSettingsFromCli:
    def test_cli_model_and_reasoning_override_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ROUTE_AGENT_MODEL", "anthropic/claude-sonnet-4-5")
        monkeypatch.setenv("ROUTE_AGENT_REASONING_EFFORT", "low")
        settings = settings_from_cli(
            model="openai/gpt-5.6-terra", reasoning_effort="high"
        )
        assert settings.model == "openai/gpt-5.6-terra"
        assert settings.reasoning_effort == "high"
        assert settings.model_provider() == "openai"

    def test_omitted_flags_keep_environment_defaults(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ROUTE_AGENT_MODEL", "openai/gpt-4o-mini")
        monkeypatch.setenv("ROUTE_AGENT_REASONING_EFFORT", "low")
        settings = settings_from_cli(no_model=True)
        assert settings.model == "openai/gpt-4o-mini"
        assert settings.reasoning_effort == "low"
        assert settings.no_model is True


class TestBoltzApiKeyFromEnv:
    def test_boltz_key_comes_from_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BOLTZ_API_KEY", "sk_bc_ws_test_example")
        settings = Settings()
        assert settings.secret_value_or_none(settings.boltz_api_key) == (
            "sk_bc_ws_test_example"
        )
        assert settings.molecular_config().boltz_api_key == "sk_bc_ws_test_example"

    def test_missing_boltz_key_stays_absent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("BOLTZ_API_KEY", raising=False)
        settings = Settings(_env_file=None)  # type: ignore[call-arg]
        assert settings.secret_value_or_none(settings.boltz_api_key) is None
