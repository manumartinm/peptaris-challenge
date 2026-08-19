from __future__ import annotations

from pathlib import Path

from route_agent.literature.sandbox import FetchAndParse, LiteratureSandbox

ARTICLE = (
    "Ruthenium catalysts used for olefin metathesis are poisoned by free thiols. "
    "Disulfide-intact peptides therefore require orthogonal protection during "
    "stapling. Iodine-mediated oxidation can also modify tyrosine and tryptophan "
    "side chains if those residues are left unprotected.\n"
) * 8


class TestFetchAndParse:
    def test_second_persist_of_same_url_reuses_cache(self, tmp_path: Path) -> None:
        sandbox = LiteratureSandbox(tmp_path / "research")
        fetcher = FetchAndParse(sandbox=sandbox)
        url = "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC123/pdf/main.pdf"

        first = fetcher.cache_document(url, ARTICLE)
        second = fetcher.cache_document(url, "Paywall stub that must not overwrite.")

        assert first.cache_hit is False
        assert second.cache_hit is True
        assert first.path == second.path
        assert first.preview
        assert "Ruthenium" in first.preview
        assert first.full_text is None
        assert second.full_text is None
        stored = Path(first.path).read_text(encoding="utf-8")
        assert "Ruthenium" in stored
        assert "Paywall stub" not in stored

    def test_short_fetch_is_thin_and_not_citeable(self, tmp_path: Path) -> None:
        sandbox = LiteratureSandbox(tmp_path / "research")
        result = FetchAndParse(sandbox=sandbox).cache_document(
            "https://pubs.acs.org/doi/pdf/10.1021/example",
            "Buy this article.\nAbstract: two sentences behind a paywall.\n",
        )

        assert result.thin_content is True
        assert result.citeable is False
        assert result.path
        assert result.preview

    def test_full_article_is_citeable_and_keeps_citations(self, tmp_path: Path) -> None:
        sandbox = LiteratureSandbox(tmp_path / "research")
        result = FetchAndParse(sandbox=sandbox).cache_document(
            "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC999/pdf/main.pdf",
            ARTICLE,
            citations=("ruthenium catalyst thiol poisoning",),
        )

        assert result.thin_content is False
        assert result.citeable is True
        assert result.citations == ("ruthenium catalyst thiol poisoning",)
        assert "Ruthenium" in Path(result.path).read_text(encoding="utf-8")

    def test_html_url_is_processed_and_cached(self, tmp_path: Path) -> None:
        sandbox = LiteratureSandbox(tmp_path / "research")
        fetcher = FetchAndParse(sandbox=sandbox)
        result = fetcher.cache_document(
            "https://pubs.acs.org/doi/10.1021/example",
            ARTICLE,
        )

        assert result.path != ""
        assert result.citeable is True
        assert result.cache_hit is False
        assert "Ruthenium" in result.preview
