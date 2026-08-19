"""Configuration and dependency checks for ``route-agent doctor``.

Checks never call a model and never print secret values. Mandatory failures
exit 3 from the CLI; a missing API key is a failure unless ``--no-model``.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from route_agent.credentials import credential_status
from route_agent.paths import (
    default_research_root,
    ensure_writable_dir,
    extracted_families_path,
    fragments_path,
    packaged_resource_path,
    schema_path,
    targets_path,
    user_cache_root,
    user_config_root,
)
from route_agent.settings import Settings, provider_for_model

CheckStatus = Literal["pass", "warning", "fail"]


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: CheckStatus
    detail: str
    required: bool = True


@dataclass(frozen=True)
class DoctorReport:
    checks: tuple[DoctorCheck, ...]
    no_model: bool

    @property
    def failed(self) -> bool:
        return any(item.status == "fail" and item.required for item in self.checks)

    def as_payload(self) -> dict[str, object]:
        return {
            "no_model": self.no_model,
            "ok": not self.failed,
            "checks": [
                {
                    "name": item.name,
                    "status": item.status,
                    "detail": item.detail,
                    "required": item.required,
                }
                for item in self.checks
            ],
        }


def run_doctor(settings: Settings, *, no_model: bool) -> DoctorReport:
    checks = (
        _python_version(),
        _packaged_resources(),
        _rdkit_import(),
        _model_provider(settings),
        _api_key(settings, no_model=no_model),
        _writable_directories(),
        _langfuse(settings),
        _boltz_key(settings),
    )
    return DoctorReport(checks=checks, no_model=no_model)


def _python_version() -> DoctorCheck:
    version = sys.version_info
    detail = f"{version.major}.{version.minor}.{version.micro}"
    if version < (3, 12):
        return DoctorCheck(
            "python",
            "fail",
            f"{detail} is too old; route-agent requires Python 3.12+",
        )
    return DoctorCheck("python", "pass", detail)


def _packaged_resources() -> DoctorCheck:
    names = (
        "extracted_families.json",
        "molecular_fragments.json",
        "ApexChem_templates_and_targets.xlsx",
        "schema.json",
        "score.py",
    )
    missing: list[str] = []
    for name in names:
        try:
            path = packaged_resource_path(name)
        except FileNotFoundError:
            missing.append(name)
            continue
        if not path.is_file():
            missing.append(name)
    if missing:
        return DoctorCheck(
            "resources",
            "fail",
            "missing packaged files: " + ", ".join(missing),
        )
    paths = (
        extracted_families_path(),
        fragments_path(),
        targets_path(),
        schema_path(),
    )
    return DoctorCheck("resources", "pass", f"{len(paths)} runtime files readable")


def _rdkit_import() -> DoctorCheck:
    try:
        from rdkit import Chem

        mol = Chem.MolFromSmiles("C")
        if mol is None:
            return DoctorCheck(
                "rdkit", "fail", "RDKit imported but cannot parse SMILES"
            )
    except Exception as exc:  # noqa: BLE001
        return DoctorCheck(
            "rdkit", "fail", f"RDKit import failed: {type(exc).__name__}"
        )
    return DoctorCheck("rdkit", "pass", "import ok")


def _model_provider(settings: Settings) -> DoctorCheck:
    provider = provider_for_model(settings.model)
    return DoctorCheck(
        "model",
        "pass",
        f"{settings.model} (provider={provider})",
    )


def _api_key(settings: Settings, *, no_model: bool) -> DoctorCheck:
    provider = settings.model_provider()
    env_value = (
        settings.secret_value_or_none(settings.openai_api_key)
        if provider == "openai"
        else settings.secret_value_or_none(settings.anthropic_api_key)
    )
    try:
        status = credential_status(provider, env_value=env_value)
    except ValueError:
        status = credential_status("anthropic", env_value=env_value)
    if status.available:
        return DoctorCheck("api_key", "pass", f"{provider} key via {status.source}")
    detail = (
        f"no {provider} API key; run `route-agent config set-api-key {provider}` "
        "or set the provider environment variable"
    )
    if no_model:
        return DoctorCheck("api_key", "warning", detail, required=False)
    return DoctorCheck("api_key", "fail", detail)


def _writable_directories() -> DoctorCheck:
    targets = (
        ("cache", user_cache_root()),
        ("config", user_config_root()),
        ("research", default_research_root()),
        ("cwd_traces", Path("traces")),
    )
    failed: list[str] = []
    for name, path in targets:
        try:
            ensure_writable_dir(path)
        except OSError as exc:
            failed.append(f"{name} ({exc})")
    if failed:
        return DoctorCheck(
            "directories",
            "fail",
            "not writable: " + "; ".join(failed),
        )
    return DoctorCheck(
        "directories", "pass", "cache, config, research, traces writable"
    )


def _langfuse(settings: Settings) -> DoctorCheck:
    public = settings.secret_value_or_none(settings.langfuse_public_key)
    secret = settings.secret_value_or_none(settings.langfuse_secret_key)
    if public and secret:
        host = settings.langfuse_host or "cloud"
        return DoctorCheck("langfuse", "pass", f"configured ({host})", required=False)
    return DoctorCheck(
        "langfuse",
        "warning",
        "not configured; tracing is optional",
        required=False,
    )


def _boltz_key(settings: Settings) -> DoctorCheck:
    if settings.secret_value_or_none(settings.boltz_api_key):
        return DoctorCheck("boltz", "pass", "BOLTZ_API_KEY set", required=False)
    return DoctorCheck(
        "boltz",
        "warning",
        "no BOLTZ_API_KEY; 3D structure is skipped",
        required=False,
    )
