"""Store and resolve provider API keys without writing them to disk.

Precedence for a live call is ``environment variable > keyring > absent``.
The keyring is a convenience for interactive installs; CI and headless
hosts should set ``OPENAI_API_KEY`` or ``ANTHROPIC_API_KEY``. Values are
never logged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PROVIDER_ENV = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}
PROVIDERS = tuple(PROVIDER_ENV)
ProviderName = Literal["openai", "anthropic"]

_SERVICE = "route-agent"


class CredentialError(RuntimeError):
    """Raised when the system keyring cannot store or read a secret."""


@dataclass(frozen=True)
class CredentialStatus:
    provider: ProviderName
    in_environment: bool
    in_keyring: bool

    @property
    def available(self) -> bool:
        return self.in_environment or self.in_keyring

    @property
    def source(self) -> str | None:
        if self.in_environment:
            return "environment"
        if self.in_keyring:
            return "keyring"
        return None


def normalize_provider(provider: str) -> ProviderName:
    name = provider.strip().lower()
    if name not in PROVIDER_ENV:
        allowed = ", ".join(PROVIDERS)
        raise ValueError(f"unknown provider {provider!r}; expected one of: {allowed}")
    return name  # type: ignore[return-value]


def set_api_key(provider: str, key: str) -> None:
    name = normalize_provider(provider)
    secret = key.strip()
    if not secret:
        raise ValueError("API key must not be empty")
    try:
        import keyring
    except ImportError as exc:
        raise CredentialError(_missing_keyring_message()) from exc
    try:
        keyring.set_password(_SERVICE, name, secret)
    except Exception as exc:  # noqa: BLE001
        raise CredentialError(_blocked_keyring_message(exc)) from exc


def get_api_key(provider: str) -> str | None:
    """Return the keyring secret for ``provider``, or None if absent."""
    name = normalize_provider(provider)
    try:
        import keyring
    except ImportError:
        return None
    try:
        value = keyring.get_password(_SERVICE, name)
    except Exception:
        return None
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def unset_api_key(provider: str) -> bool:
    """Delete the stored key. Returns True when a value was present."""
    name = normalize_provider(provider)
    try:
        import keyring
    except ImportError as exc:
        raise CredentialError(_missing_keyring_message()) from exc
    try:
        existing = keyring.get_password(_SERVICE, name)
        if not existing:
            return False
        keyring.delete_password(_SERVICE, name)
        return True
    except Exception as exc:  # noqa: BLE001
        raise CredentialError(_blocked_keyring_message(exc)) from exc


def credential_status(provider: str, *, env_value: str | None) -> CredentialStatus:
    name = normalize_provider(provider)
    return CredentialStatus(
        provider=name,
        in_environment=bool(env_value),
        in_keyring=get_api_key(name) is not None,
    )


def _missing_keyring_message() -> str:
    return (
        "the system keyring package is not available; "
        "set OPENAI_API_KEY or ANTHROPIC_API_KEY instead"
    )


def _blocked_keyring_message(exc: Exception) -> str:
    return (
        f"the system keyring is unavailable ({type(exc).__name__}); "
        "set OPENAI_API_KEY or ANTHROPIC_API_KEY for CI or headless hosts"
    )
