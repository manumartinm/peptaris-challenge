from __future__ import annotations

from typing import Any, Literal


class ProviderWebTools:
    SEARCH_MAX_USES = 3
    FETCH_MAX_USES = 2
    MAX_CONTENT_TOKENS = 30000
    ANTHROPIC_SEARCH_TYPE = "web_search_20250305"
    ANTHROPIC_FETCH_TYPE = "web_fetch_20250910"
    OPENAI_SEARCH_TYPE = "web_search"

    def __init__(
        self,
        allowed_domains: tuple[str, ...],
        provider: Literal["anthropic", "openai"] = "anthropic",
    ) -> None:
        self._allowed_domains = allowed_domains
        self._provider = provider

    def native_tools(self) -> list[dict[str, Any]]:
        if self._provider == "openai":
            return [self._openai_web_search()]
        return [self._anthropic_web_search(), self._anthropic_web_fetch()]

    def _anthropic_web_search(self) -> dict[str, Any]:
        return {
            "type": self.ANTHROPIC_SEARCH_TYPE,
            "name": "web_search",
            "max_uses": self.SEARCH_MAX_USES,
            "allowed_domains": list(self._allowed_domains),
        }

    def _anthropic_web_fetch(self) -> dict[str, Any]:
        return {
            "type": self.ANTHROPIC_FETCH_TYPE,
            "name": "web_fetch",
            "max_uses": self.FETCH_MAX_USES,
            "allowed_domains": list(self._allowed_domains),
            "max_content_tokens": self.MAX_CONTENT_TOKENS,
            "citations": {"enabled": True},
        }

    def _openai_web_search(self) -> dict[str, Any]:
        return {
            "type": self.OPENAI_SEARCH_TYPE,
            "filters": {"allowed_domains": list(self._allowed_domains)},
            "search_context_size": "low",
        }
