from __future__ import annotations

from pathlib import Path

from route_agent.literature.audit import AuditRef
from route_agent.literature.sandbox import FetchAndParse, LiteratureSandbox
from tests.support.validation_case import ValidationCase

PAPER = "# Paper\n\nPd-labile Alloc survives Fmoc/tBu.\n"


class TestAuditRef(ValidationCase):
    def test_external_fails_when_source_is_not_cached(self, tmp_path: Path) -> None:
        sandbox = LiteratureSandbox(tmp_path / "research")
        auditor = AuditRef(sandbox=sandbox, families_path=self.families_path)
        result = auditor.verify_citation(
            kind="external",
            ref_or_source="https://pubs.acs.org/missing",
            basis="Alloc",
        )

        assert result.verified is False
        assert result.reason == "source_not_cached"

    def test_external_fails_when_basis_terms_are_absent(self, tmp_path: Path) -> None:
        sandbox = LiteratureSandbox(tmp_path / "research")
        fetched = FetchAndParse(sandbox=sandbox).cache_document(
            "https://pubs.acs.org/doi/pdf/10.1021/example",
            PAPER,
        )
        auditor = AuditRef(sandbox=sandbox, families_path=self.families_path)
        result = auditor.verify_citation(
            kind="external",
            ref_or_source="https://pubs.acs.org/doi/pdf/10.1021/example",
            basis="hydrazine ivDde",
        )

        assert fetched.cache_hit is False
        assert result.verified is False
        assert result.reason == "basis_not_found"

    def test_external_passes_when_cached_file_contains_basis(
        self, tmp_path: Path
    ) -> None:
        sandbox = LiteratureSandbox(tmp_path / "research")
        FetchAndParse(sandbox=sandbox).cache_document(
            "https://pubs.acs.org/doi/pdf/10.1021/example",
            PAPER,
        )
        auditor = AuditRef(sandbox=sandbox, families_path=self.families_path)
        result = auditor.verify_citation(
            kind="external",
            ref_or_source="https://pubs.acs.org/doi/pdf/10.1021/example",
            basis="Alloc Fmoc",
        )

        assert result.verified is True
        assert result.path is not None

    def test_corpus_ref_verifies_existing_excerpt(self, tmp_path: Path) -> None:
        result = AuditRef(
            sandbox=LiteratureSandbox(tmp_path / "research"),
            families_path=self.families_path,
        ).verify_citation(
            kind="corpus",
            ref_or_source="ApexChem_Synthesis_Reactions_by_AminoAcid:06_Lipidation:25",
            basis="ivDde",
        )

        assert result.verified is True
        assert result.ref_row == 25

    def test_corpus_ref_verifies_when_basis_is_a_paraphrase(
        self, tmp_path: Path
    ) -> None:
        result = AuditRef(
            sandbox=LiteratureSandbox(tmp_path / "research"),
            families_path=self.families_path,
        ).verify_citation(
            kind="corpus",
            ref_or_source="ApexChem_Synthesis_Reactions_by_AminoAcid:06_Lipidation:14",
            basis=(
                "Alloc/Pd deprotection is the preferred lipidation handle "
                "when Trt-protected histidine is present"
            ),
        )

        assert result.verified is True
        assert result.ref_row == 14

    def test_corpus_ref_fails_when_basis_not_in_excerpt(self, tmp_path: Path) -> None:
        result = AuditRef(
            sandbox=LiteratureSandbox(tmp_path / "research"),
            families_path=self.families_path,
        ).verify_citation(
            kind="corpus",
            ref_or_source="ApexChem_Synthesis_Reactions_by_AminoAcid:06_Lipidation:25",
            basis="olefin metathesis Grubbs catalyst poisoning",
        )

        assert result.verified is False
        assert result.reason == "basis_not_found"

    def test_unknown_corpus_ref_still_fails(self, tmp_path: Path) -> None:
        result = AuditRef(
            sandbox=LiteratureSandbox(tmp_path / "research"),
            families_path=self.families_path,
        ).verify_citation(
            kind="corpus",
            ref_or_source="ApexChem_Synthesis_Reactions_by_AminoAcid:06_Lipidation:9999",
            basis="ivDde",
        )

        assert result.verified is False
        assert result.reason == "corpus_ref_not_found"
