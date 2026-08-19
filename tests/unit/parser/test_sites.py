from __future__ import annotations

from route_agent.models.request import ResolvedSite, SiteAtom
from route_agent.parser.sites import SiteValidator, resolve_site_token
from tests.support.validation_case import (
    GLUCAGON,
    OCTREOTIDE,
    TERIPARATIDE,
    ValidationCase,
)


class TestSiteValidator(ValidationCase):
    def test_single_position_site(self) -> None:
        result = self.validate_sites(GLUCAGON, "K12")

        assert result.errors == ()
        assert result.sites_resolved[0].atoms[0].index == 12
        assert result.site_map[0].requested == "K12"
        assert result.site_map[0].resolved == "K12"
        assert result.site_map[0].residue == "Lys"

    def test_comma_list_echoes_whole_token(self) -> None:
        result = self.validate_sites(TERIPARATIDE, "V21,R25")

        mapped = [
            (entry.requested, entry.resolved, entry.residue)
            for entry in result.site_map
        ]
        assert mapped == [
            ("V21,R25", "V21", "Val"),
            ("V21,R25", "R25", "Arg"),
        ]

    def test_range_expands_to_endpoints_only(self) -> None:
        result = self.validate_sites(OCTREOTIDE, "C2-C7", family="disulfide")

        assert [(entry.requested, entry.resolved) for entry in result.site_map] == [
            ("C2-C7", "C2"),
            ("C2-C7", "C7"),
        ]

    def test_multi_range_triple_disulfide(self) -> None:
        result = self.validate_sites(
            "CCEYCCNPACTGCY", "C1-C6, C2-C10, C5-C13", family="disulfide"
        )

        assert [entry.resolved for entry in result.site_map] == [
            "C1",
            "C6",
            "C2",
            "C10",
            "C5",
            "C13",
        ]
        assert {entry.requested for entry in result.site_map} == {
            "C1-C6, C2-C10, C5-C13"
        }

    def test_keyword_sites(self) -> None:
        both = self.validate_sites("ACDE", "both termini", family="cyclization")
        whole = self.validate_sites("ACDE", "whole sequence", family="retro_inverso")
        nterm = self.validate_sites("ACDE", "N-term", family="n_term_acetylation")

        assert [(entry.resolved, entry.residue) for entry in both.site_map] == [
            ("N-term", None),
            ("C-term", None),
        ]
        assert [
            (entry.requested, entry.resolved, entry.residue) for entry in whole.site_map
        ] == [("whole sequence", "whole sequence", None)]
        assert nterm.site_map[0].resolved == "N-term"

    def test_resolve_site_token_keeps_staple_as_one_bridge(self) -> None:
        site = ResolvedSite(
            modification_ref=0,
            requested_token="V21,R25",
            atoms=(
                SiteAtom(kind="position", letter="V", index=21, token="V21"),
                SiteAtom(kind="position", letter="R", index=25, token="R25"),
            ),
        )

        assert resolve_site_token(site) == "V21,R25"

    def test_resolve_site_token_rewrites_remapped_positions_in_place(self) -> None:
        site = ResolvedSite(
            modification_ref=0,
            requested_token="C2-C7",
            atoms=(
                SiteAtom(kind="position", letter="C", index=7, token="C7"),
                SiteAtom(kind="position", letter="C", index=2, token="C2"),
            ),
        )

        assert resolve_site_token(site) == "C7-C2"

    def test_resolve_site_token_keeps_keywords(self) -> None:
        site = ResolvedSite(
            modification_ref=0,
            requested_token="both termini",
            atoms=(
                SiteAtom(kind="n_term", token="N-term"),
                SiteAtom(kind="c_term", token="C-term"),
            ),
        )

        assert resolve_site_token(site) == "both termini"

    def test_whitespace_around_separators_is_insignificant(self) -> None:
        result = self.validate_sites(TERIPARATIDE, " V21 , R25 ")

        assert [entry.resolved for entry in result.site_map] == ["V21", "R25"]
        assert result.sites_resolved[0].requested_token == " V21 , R25 "

    def test_letter_mismatch_is_site_invalid(self) -> None:
        result = self.validate_sites(GLUCAGON, "K13")

        assert result.errors[0].conflict_kind == "site_invalid"
        assert result.errors[0].code == "SITE_LETTER_MISMATCH"
        assert result.conflicts[0].kind == "site_invalid"
        assert result.conflicts[0].affected == ("K13",)

    def test_out_of_range_is_site_invalid(self) -> None:
        result = self.validate_sites("ACDE", "K12")

        assert result.errors[0].code == "SITE_OUT_OF_RANGE"
        assert result.errors[0].conflict_kind == "site_invalid"

    def test_malformed_token_is_site_invalid(self) -> None:
        result = self.validate_sites("ACDE", "12K")

        assert result.errors[0].code == "SITE_MALFORMED"
        assert result.errors[0].conflict_kind == "site_invalid"

    def test_parent_features_do_not_enter_site_map(self) -> None:
        request = self.request(
            request_id="T-SITE",
            parent_name="octreotide",
            sequence=OCTREOTIDE,
            parent_c_terminus="alcohol",
            parent_features=["disulfide C2-C7"],
            modifications=[{"family": "pegylation", "site": "K5"}],
        )
        residues = self.validate_sequence(request).residues
        result = SiteValidator().validate_modification_sites(request, residues)

        assert [entry.requested for entry in result.site_map] == ["K5"]

    def test_identity_index_map_leaves_site_map_unchanged(self) -> None:
        request = self.request(
            request_id="T-SITE",
            sequence=GLUCAGON,
            modifications=[{"family": "lipidation", "site": "K12"}],
        )
        remapped = self.remap_sites(request)

        assert remapped.site_map[0].requested == "K12"
        assert remapped.site_map[0].resolved == "K12"
        assert remapped.site_map[0].residue == "Lys"
        assert remapped.site_map[0].note is None
        assert remapped.sites_resolved[0].atoms[0].token == "K12"

    def test_letter_change_updates_resolved_token_and_note(self) -> None:
        request = self.request(
            request_id="T-SITE",
            parent_name="glucagon",
            sequence=GLUCAGON,
            modifications=[
                {"family": "special_residues", "site": "M27", "detail": "Met->Arg"}
            ],
        )
        remapped = self.remap_sites(request)

        assert remapped.site_map[0].requested == "M27"
        assert remapped.site_map[0].resolved == "R27"
        assert remapped.site_map[0].residue == "Arg"
        assert remapped.site_map[0].note is not None
        assert "M27" in remapped.site_map[0].note
        assert "R27" in remapped.site_map[0].note
        assert remapped.sites_resolved[0].atoms[0].letter == "R"
        assert remapped.sites_resolved[0].atoms[0].index == 27

    def test_retro_inverso_reindexes_position_and_keeps_keyword(self) -> None:
        request = self.request(
            request_id="T-SITE",
            parent_name="alpha-MSH",
            sequence="SYSMEHFRWGKPV",
            parent_c_terminus="amide",
            modifications=[
                {"family": "retro_inverso", "site": "whole sequence"},
                {"family": "lipidation", "site": "K11", "detail": "C16"},
            ],
        )
        remapped = self.remap_sites(request)
        lipid = next(entry for entry in remapped.site_map if entry.requested == "K11")
        whole = next(
            entry for entry in remapped.site_map if entry.requested == "whole sequence"
        )
        lipid_site = next(
            site for site in remapped.sites_resolved if site.requested_token == "K11"
        )

        assert lipid.resolved == "K3"
        assert lipid.residue == "Lys"
        assert lipid.note is not None
        assert "K11" in lipid.note
        assert "K3" in lipid.note
        assert whole.resolved == "whole sequence"
        assert whole.note is None
        assert lipid_site.atoms[0].token == "K3"

    def test_product_frame_detail_conflicts_with_parent_site(self) -> None:
        request = self.request(
            request_id="T-SITE-FRAME",
            parent_name="substance P",
            sequence="RPKPQQFFGLM",
            parent_c_terminus="amide",
            modifications=[
                {"family": "retro_inverso", "site": "whole sequence"},
                {
                    "family": "lipidation",
                    "site": "K3",
                    "detail": "C16 at position 3 of the retro-inverso product",
                },
            ],
        )
        remapped = self.remap_sites(request)

        assert any(item.kind == "site_invalid" for item in remapped.conflicts)
        assert any(error.conflict_kind == "site_invalid" for error in remapped.errors)

    def test_honest_retro_inverso_remap_is_not_invalid(self) -> None:
        request = self.request(
            request_id="T-SITE-FRAME-OK",
            parent_name="substance P",
            sequence="RPKPQQFFGLM",
            parent_c_terminus="amide",
            modifications=[
                {"family": "retro_inverso", "site": "whole sequence"},
                {"family": "lipidation", "site": "K3", "detail": "C16 palmitoyl"},
            ],
        )
        remapped = self.remap_sites(request)
        lipid = next(entry for entry in remapped.site_map if entry.requested == "K3")

        assert lipid.resolved == "K9"
        assert lipid.note is not None
        assert "K3" in lipid.note
        assert "K9" in lipid.note
        assert not any(item.kind == "site_invalid" for item in remapped.conflicts)
