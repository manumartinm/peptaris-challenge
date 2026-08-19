from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook  # type: ignore[import-untyped]

from route_agent.corpus import CorpusRepository
from tests.support.validation_case import ValidationCase


class TestLookupTarget(ValidationCase):
    def test_reads_receptor_class_from_workbook(self) -> None:
        workbook = self.data_dir / "ApexChem_templates_and_targets.xlsx"
        result = CorpusRepository(
            self.families_path, targets_path=workbook
        ).lookup_target("Ipamorelin")

        assert result.available is True
        assert result.peptide == "Ipamorelin"
        assert result.receptor_target is not None
        assert "Ghrelin" in result.receptor_target
        assert result.receptor_class == "GPCR class A"
        assert result.ligand_role == "agonist"

    def test_missing_workbook_is_unavailable_not_invented(self, tmp_path: Path) -> None:
        result = CorpusRepository(
            self.families_path, targets_path=tmp_path / "missing.xlsx"
        ).lookup_target("Ipamorelin")

        assert result.available is False
        assert result.reason == "workbook_unavailable"
        assert result.receptor_target is None
        assert result.receptor_class is None
        assert result.invariant_windows == ()
        assert result.sar_precedents == ()

    def test_reads_optional_sar_columns_without_inventing(self, tmp_path: Path) -> None:
        path = tmp_path / "targets.xlsx"
        workbook = Workbook()
        master = workbook.active
        assert master is not None
        master.title = "Target_Peptide_Master"
        master.append(
            [
                "Peptide",
                "Receptor Target",
                "Receptor Class",
                "Ligand Role",
                "Invariant Windows",
                "SAR Precedents",
                "Sequence",
            ]
        )
        master.append(
            [
                "Glucagon",
                "GCGR",
                "GPCR class B1",
                "agonist",
                "1-8; 27-29",
                "K12 lipid ok; N-term lipid abolishes agonism",
                "not-parseable display",
            ]
        )
        workbook.save(path)

        result = CorpusRepository(self.families_path, targets_path=path).lookup_target(
            "glucagon"
        )
        assert result.available is True
        assert result.receptor_class == "GPCR class B1"
        assert result.invariant_windows == ("1-8", "27-29")
        assert result.sar_precedents == (
            "K12 lipid ok",
            "N-term lipid abolishes agonism",
        )
