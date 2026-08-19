"""Runtime settings: model, credentials, packaged paths, and molecular knobs."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from route_agent.credentials import get_api_key, normalize_provider
from route_agent.paths import (
    default_env_files,
    default_research_root,
    extracted_families_path,
    fragments_path,
    targets_path,
)

if TYPE_CHECKING:
    from route_agent.molecular.analysis import MolecularConfig

DEFAULT_JOURNAL_ALLOWLIST = (
    "pubs.acs.org",
    "onlinelibrary.wiley.com",
    "pubs.rsc.org",
    "nature.com",
    "ncbi.nlm.nih.gov",
)


def langchain_model_spec(model: str) -> str:
    """Map LiteLLM `provider/model` to LangChain `provider:model`."""
    if ":" in model:
        return model
    provider, separator, name = model.partition("/")
    if separator and name:
        return f"{provider}:{name}"
    return model


def uses_openai_model(model: str) -> bool:
    return langchain_model_spec(model).startswith("openai:")


def uses_gpt5_reasoning_model(model: str) -> bool:
    name = langchain_model_spec(model).split(":", 1)[-1].lower()
    return "gpt-5" in name and not name.startswith("gpt-5-chat")


def provider_for_model(model: str) -> str:
    spec = langchain_model_spec(model)
    provider, separator, _name = spec.partition(":")
    if separator:
        return provider
    if model.startswith("openai/") or model.startswith("openai:"):
        return "openai"
    return "anthropic"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=default_env_files(),
        extra="ignore",
        populate_by_name=True,
    )

    model: str = Field(default="anthropic/claude-sonnet-4-5", alias="ROUTE_AGENT_MODEL")
    anthropic_api_key: SecretStr | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    openai_api_key: SecretStr | None = Field(default=None, alias="OPENAI_API_KEY")
    langfuse_public_key: SecretStr | None = Field(
        default=None, alias="LANGFUSE_PUBLIC_KEY"
    )
    langfuse_secret_key: SecretStr | None = Field(
        default=None, alias="LANGFUSE_SECRET_KEY"
    )
    langfuse_host: str | None = Field(default=None, alias="LANGFUSE_HOST")
    boltz_api_key: SecretStr | None = Field(default=None, alias="BOLTZ_API_KEY")
    boltz_timeout_s: float = Field(default=180.0, alias="ROUTE_AGENT_BOLTZ_TIMEOUT")
    extracted_families_path: Path = Field(default_factory=extracted_families_path)
    targets_path: Path = Field(default_factory=targets_path)
    fragments_path: Path = Field(default_factory=fragments_path)
    research_root: Path = Field(default_factory=default_research_root)
    journal_allowlist: tuple[str, ...] = Field(
        default=DEFAULT_JOURNAL_ALLOWLIST, alias="JOURNAL_ALLOWLIST"
    )
    check_timeout_s: float = Field(default=180.0, alias="ROUTE_AGENT_CHECK_TIMEOUT")
    molecular_ph: float = Field(default=7.4, alias="ROUTE_AGENT_MOLECULAR_PH")
    molecular_num_conformers: int = Field(
        default=20, alias="ROUTE_AGENT_MOLECULAR_CONFORMERS"
    )
    molecular_seed: int = Field(default=17, alias="ROUTE_AGENT_MOLECULAR_SEED")
    molecular_timeout_s: float = Field(
        default=60.0, alias="ROUTE_AGENT_MOLECULAR_TIMEOUT"
    )
    molecular_max_heavy_atoms: int = Field(
        default=500, alias="ROUTE_AGENT_MOLECULAR_MAX_HEAVY"
    )
    molecular_skip_3d: bool = Field(
        default=False, alias="ROUTE_AGENT_MOLECULAR_SKIP_3D"
    )
    no_model: bool = False
    reasoning_effort: str = Field(
        default="medium", alias="ROUTE_AGENT_REASONING_EFFORT"
    )

    @field_validator("journal_allowlist", mode="before")
    @classmethod
    def split_journal_allowlist(cls, value: object) -> object:
        if isinstance(value, str):
            return tuple(item.strip() for item in value.split(",") if item.strip())
        return value

    def secret_value_or_none(self, field: SecretStr | None) -> str | None:
        if field is None:
            return None
        value = field.get_secret_value()
        return value or None

    def molecular_config(self) -> MolecularConfig:
        from route_agent.molecular.analysis import MolecularConfig

        return MolecularConfig(
            ph=self.molecular_ph,
            num_conformers=self.molecular_num_conformers,
            seed=self.molecular_seed,
            timeout_s=self.molecular_timeout_s,
            max_heavy_atoms=self.molecular_max_heavy_atoms,
            skip_3d=self.molecular_skip_3d,
            no_model=self.no_model,
            boltz_api_key=self.secret_value_or_none(self.boltz_api_key),
            boltz_timeout_s=self.boltz_timeout_s,
        )

    def model_provider(self) -> str:
        return provider_for_model(self.model)

    def provider_api_key(self) -> str | None:
        """Resolve the active provider key: environment, then keyring."""
        provider = self.model_provider()
        from_env = self._env_api_key(provider)
        if from_env:
            return from_env
        try:
            return get_api_key(normalize_provider(provider))
        except ValueError:
            return get_api_key("anthropic") or get_api_key("openai")

    def apply_provider_credentials(self) -> str | None:
        """Expose the resolved key to LangChain/LiteLLM without logging it."""
        key = self.provider_api_key()
        if key is None:
            return None
        env_name = (
            "OPENAI_API_KEY"
            if self.model_provider() == "openai"
            else "ANTHROPIC_API_KEY"
        )
        os.environ.setdefault(env_name, key)
        return key

    def _env_api_key(self, provider: str) -> str | None:
        if provider == "openai":
            return self.secret_value_or_none(self.openai_api_key)
        if provider == "anthropic":
            return self.secret_value_or_none(self.anthropic_api_key)
        anthropic = self.secret_value_or_none(self.anthropic_api_key)
        return anthropic or self.secret_value_or_none(self.openai_api_key)
