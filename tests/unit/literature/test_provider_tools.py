from __future__ import annotations

from route_agent.literature.provider_tools import ProviderWebTools
from route_agent.settings import DEFAULT_JOURNAL_ALLOWLIST


class TestProviderWebTools:
    def test_anthropic_web_search_budget_and_domains(self) -> None:
        spec = ProviderWebTools(
            DEFAULT_JOURNAL_ALLOWLIST, provider="anthropic"
        ).native_tools()[0]

        assert spec["type"] == "web_search_20250305"
        assert spec["name"] == "web_search"
        assert spec["max_uses"] == 3
        assert spec["allowed_domains"] == list(DEFAULT_JOURNAL_ALLOWLIST)
        assert "ncbi.nlm.nih.gov" in spec["allowed_domains"]
        assert "nature.com" in spec["allowed_domains"]
        assert "sciencedirect.com" not in spec["allowed_domains"]

    def test_anthropic_web_fetch_enables_citations(self) -> None:
        spec = ProviderWebTools(
            DEFAULT_JOURNAL_ALLOWLIST, provider="anthropic"
        ).native_tools()[1]

        assert spec["type"] == "web_fetch_20250910"
        assert spec["name"] == "web_fetch"
        assert spec["max_uses"] == 2
        assert spec["max_content_tokens"] == 30000
        assert spec["citations"] == {"enabled": True}
        assert spec["allowed_domains"] == list(DEFAULT_JOURNAL_ALLOWLIST)

    def test_openai_web_search_is_responses_hosted_tool(self) -> None:
        spec = ProviderWebTools(
            DEFAULT_JOURNAL_ALLOWLIST, provider="openai"
        ).native_tools()[0]

        assert spec["type"] == "web_search"
        assert spec["search_context_size"] == "low"
        assert spec["filters"]["allowed_domains"] == list(DEFAULT_JOURNAL_ALLOWLIST)
        assert "ncbi.nlm.nih.gov" in spec["filters"]["allowed_domains"]
        assert "name" not in spec
        assert spec["filters"]["allowed_domains"].count("sciencedirect.com") == 0
