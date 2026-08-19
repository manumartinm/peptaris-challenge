from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from route_agent.corpus import CorpusRepository
from route_agent.models.corpus import ExtractedFamiliesView
from route_agent.models.request import ModificationFamily
from tests.support.validation_case import GLUCAGON, ValidationCase


def _catalog(
    *,
    family_order: list[str],
    families: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "2.0.0",
        "source_workbook": "ApexChem_Synthesis_Reactions_by_AminoAcid",
        "family_order": family_order,
        "families": families
        if families is not None
        else {
            name: {"sheet": f"{index:02d}_{name}"}
            for index, name in enumerate(family_order, start=1)
        },
    }


class TestCorpusRepository(ValidationCase):
    def test_binds_known_family_to_sheet_and_processes(self) -> None:
        request = self.request(
            request_id="T-FAM",
            parent_name="glucagon",
            sequence=GLUCAGON,
            modifications=[{"family": "lipidation", "site": "K12"}],
        )
        bindings, errors = CorpusRepository(self.families_path).bind_families(request)

        assert errors == ()
        assert bindings[0].family == ModificationFamily.LIPIDATION
        assert bindings[0].sheet == "06_Lipidation"
        assert bindings[0].process_ids
        assert bindings[0].process_ids[0] == "alloc_lipidation"
        assert bindings[0].provenance[0].kind == "corpus"
        ref = bindings[0].provenance[0].ref
        assert ref is not None
        assert ref.startswith(
            "ApexChem_Synthesis_Reactions_by_AminoAcid:06_Lipidation:"
        )

    def test_requested_handle_is_tried_before_catalog_order(self) -> None:
        request = self.request(
            request_id="T-MTT",
            parent_name="alpha-MSH",
            sequence="SYSMEHFRWGKPV",
            modifications=[
                {
                    "family": "lipidation",
                    "site": "K11",
                    "detail": "C16 palmitoyl via gGlu; use a Lys(Mtt) handle",
                }
            ],
        )
        bindings, errors = CorpusRepository(self.families_path).bind_families(request)

        assert errors == ()
        assert bindings[0].process_ids[0] == "mtt_lipidation"
        assert "alloc_lipidation" in bindings[0].process_ids
        ref = bindings[0].provenance[0].ref
        assert ref is not None
        assert ref.startswith(
            "ApexChem_Synthesis_Reactions_by_AminoAcid:06_Lipidation:"
        )

    def test_unknown_family_in_file_is_internal_error(self, tmp_path: Path) -> None:
        path = tmp_path / "families.json"
        path.write_text(json.dumps(_catalog(family_order=[])), encoding="utf-8")
        request = self.request(
            request_id="T-FAM",
            parent_name="glucagon",
            sequence="ACDE",
            modifications=[{"family": "lipidation", "site": "C2"}],
        )
        bindings, errors = CorpusRepository(path).bind_families(request)

        assert bindings == ()
        assert errors[0].code == "FAMILY_UNBOUND"
        assert errors[0].conflict_kind is None

    def test_rejects_unsupported_schema_version(self, tmp_path: Path) -> None:
        path = tmp_path / "families.json"
        payload = _catalog(family_order=["lipidation"])
        payload["schema_version"] = "9.9.9"
        path.write_text(json.dumps(payload), encoding="utf-8")
        repo = CorpusRepository(path)
        with pytest.raises(ValueError, match="schema_version"):
            repo.bind_families(
                self.request(
                    request_id="T-VER",
                    sequence="ACDE",
                    modifications=[{"family": "lipidation", "site": "C2"}],
                )
            )

    def test_bindings_follow_family_order_not_request_order(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "families.json"
        path.write_text(
            json.dumps(
                _catalog(
                    family_order=[
                        "special_residues",
                        "n_term_acetylation",
                        "lipidation",
                    ]
                )
            ),
            encoding="utf-8",
        )
        request = self.request(
            request_id="T-ORDER",
            parent_name="glucagon",
            sequence=GLUCAGON,
            modifications=[
                {"family": "lipidation", "site": "K12"},
                {"family": "special_residues", "site": "M27", "detail": "Met->Nle"},
                {"family": "n_term_acetylation", "site": "N-term"},
            ],
        )
        original = tuple(
            (item.family, item.site, item.detail) for item in request.modifications
        )

        bindings, errors = CorpusRepository(path).bind_families(request)

        assert errors == ()
        assert [binding.family.value for binding in bindings] == [
            "special_residues",
            "n_term_acetylation",
            "lipidation",
        ]
        assert [binding.modification_ref for binding in bindings] == [1, 2, 0]
        assert (
            tuple(
                (item.family, item.site, item.detail) for item in request.modifications
            )
            == original
        )

    def test_same_family_bindings_keep_request_index_order(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "families.json"
        path.write_text(
            json.dumps(_catalog(family_order=["special_residues", "lipidation"])),
            encoding="utf-8",
        )
        request = self.request(
            request_id="T-TIE",
            parent_name="glucagon",
            sequence=GLUCAGON,
            modifications=[
                {"family": "lipidation", "site": "K12"},
                {"family": "special_residues", "site": "M27", "detail": "Met->Nle"},
                {"family": "lipidation", "site": "K12", "detail": "C16"},
            ],
        )

        bindings, errors = CorpusRepository(path).bind_families(request)

        assert errors == ()
        assert [binding.family.value for binding in bindings] == [
            "special_residues",
            "lipidation",
            "lipidation",
        ]
        assert [binding.modification_ref for binding in bindings] == [1, 0, 2]

    def test_family_order_rejects_duplicates(self) -> None:
        with pytest.raises(ValidationError, match="family_order"):
            ExtractedFamiliesView.model_validate(
                _catalog(
                    family_order=["lipidation", "lipidation"],
                    families={"lipidation": {"sheet": "06_Lipidation"}},
                )
            )

    def test_family_order_rejects_missing_family(self) -> None:
        with pytest.raises(ValidationError, match="family_order"):
            ExtractedFamiliesView.model_validate(
                _catalog(
                    family_order=["lipidation"],
                    families={
                        "lipidation": {"sheet": "06_Lipidation"},
                        "special_residues": {"sheet": "02_Special_Residues"},
                    },
                )
            )

    def test_family_order_rejects_unknown_family(self) -> None:
        with pytest.raises(ValidationError, match="family_order"):
            ExtractedFamiliesView.model_validate(
                _catalog(
                    family_order=["lipidation", "special_residues"],
                    families={"lipidation": {"sheet": "06_Lipidation"}},
                )
            )

    def test_multi_bridge_site_stays_one_atomic_binding(self, tmp_path: Path) -> None:
        path = tmp_path / "families.json"
        path.write_text(
            json.dumps(_catalog(family_order=["disulfide"])),
            encoding="utf-8",
        )
        request = self.request(
            request_id="T-BRIDGE",
            parent_name="linaclotide",
            sequence="CCEYCCNPACTGCY",
            modifications=[
                {
                    "family": "disulfide",
                    "site": "C1-C6, C2-C10, C5-C13",
                    "detail": "three-bridge",
                }
            ],
        )

        bindings, errors = CorpusRepository(path).bind_families(request)

        assert errors == ()
        assert len(bindings) == 1
        assert bindings[0].site is None
        assert bindings[0].modification_ref == 0
        assert bindings[0].family == ModificationFamily.DISULFIDE

    def test_single_bridge_site_does_not_expand(self, tmp_path: Path) -> None:
        path = tmp_path / "families.json"
        path.write_text(
            json.dumps(_catalog(family_order=["disulfide"])),
            encoding="utf-8",
        )
        request = self.request(
            request_id="T-SINGLE",
            parent_name="test",
            sequence="CDEFGHC",
            modifications=[{"family": "disulfide", "site": "C1-C7"}],
        )

        bindings, errors = CorpusRepository(path).bind_families(request)

        assert errors == ()
        assert len(bindings) == 1
        assert bindings[0].site is None

    def test_staple_comma_pair_is_one_bridge_not_two_bindings(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "families.json"
        path.write_text(
            json.dumps(_catalog(family_order=["hydrocarbon_stapling"])),
            encoding="utf-8",
        )
        request = self.request(
            request_id="REQ-03",
            parent_name="teriparatide",
            sequence="SVSEIQLMHNLGKHLNSMERVEWLRKKLQDVHNF",
            modifications=[
                {
                    "family": "hydrocarbon_stapling",
                    "site": "V21,R25",
                    "detail": "i,i+4 all-hydrocarbon staple",
                }
            ],
        )

        bindings, errors = CorpusRepository(path).bind_families(request)

        assert errors == ()
        assert len(bindings) == 1
        assert bindings[0].site is None
        assert bindings[0].modification_ref == 0
