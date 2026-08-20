from __future__ import annotations

import pytest

from route_agent.parser.policy import ProtectingGroupCensus
from route_agent.parser.sequence import SequenceValidator
from tests.support.validation_case import (
    GLUCAGON,
    OCTREOTIDE,
    TERIPARATIDE,
    ValidationCase,
)


class TestProtectingGroupCensus(ValidationCase):
    def test_applies_hardcoded_fmoc_tbu_map(self) -> None:
        result = self.census(
            request_id="T-PG",
            parent_name="glucagon",
            sequence="CRKDY",
            modifications=[{"family": "n_methylation", "site": "C1"}],
        )

        assert result.ledger.protected == {
            "C1": "Trt",
            "R2": "Pbf",
            "K3": "Boc",
            "D4": "OtBu",
            "Y5": "tBu",
        }
        assert result.ledger.policy_version == "fmoc-tbu-v1"
        assert result.ledger.provenance[0].kind == "inference"

    def test_branch_target_starts_pending(self) -> None:
        result = self.census(
            request_id="REQ-12",
            parent_name="teriparatide",
            sequence=TERIPARATIDE,
            modifications=[
                {"family": "pegylation", "site": "N-term", "detail": "Fmoc-PEG8"},
                {"family": "lipidation", "site": "K13", "detail": "C16 via gGlu"},
            ],
        )

        assert result.ledger.protected["K13"] == "pending"
        assert result.ledger.protected["N-term"] == "pending"
        assert result.ledger.protected["K26"] == "Boc"

    def test_unknown_residue_is_reported_not_guessed(self) -> None:
        result = self.census(
            request_id="T-PG",
            parent_name="octreotide",
            sequence=OCTREOTIDE,
            parent_c_terminus="alcohol",
            modifications=[{"family": "pegylation", "site": "K5"}],
        )

        assert "X8" not in result.ledger.protected
        assert result.errors[0].code == "PROTECTING_GROUP_UNKNOWN"
        assert result.errors[0].conflict_kind is None

    def test_census_uses_resolved_letter_not_parent(self) -> None:
        result = self.census(
            request_id="T-PG",
            parent_name="glucagon",
            sequence=GLUCAGON,
            modifications=[
                {"family": "special_residues", "site": "M27", "detail": "Met->Arg"}
            ],
        )

        assert result.ledger.protected["R27"] == "Pbf"
        assert "M27" not in result.ledger.protected

    def test_nonstandard_substitution_is_unknown_at_resolved_token(self) -> None:
        result = self.census(
            request_id="T-PG",
            parent_name="glucagon",
            sequence=GLUCAGON,
            modifications=[
                {"family": "special_residues", "site": "M27", "detail": "Met->Nle"}
            ],
        )

        assert "X27" not in result.ledger.protected
        assert "M27" not in result.ledger.protected
        assert result.errors[0].code == "PROTECTING_GROUP_UNKNOWN"
        assert result.errors[0].input_snapshot["token"] == "X27"

    def test_pending_target_uses_remapped_index_after_retro_inverso(self) -> None:
        result = self.census(
            request_id="T-PG",
            parent_name="alpha-MSH",
            sequence="SYSMEHFRWGKPV",
            parent_c_terminus="amide",
            modifications=[
                {"family": "retro_inverso", "site": "whole sequence"},
                {"family": "lipidation", "site": "K11", "detail": "C16"},
            ],
        )

        assert result.ledger.protected["K3"] == "pending"
        assert "K11" not in result.ledger.protected

    def test_census_base_assigns_defaults_without_pending_targets(self) -> None:
        residues = SequenceValidator().validate_parent_sequence("CRKDY", {}).residues
        result = ProtectingGroupCensus().census_base(residues)

        assert result.ledger.protected == {
            "C1": "Trt",
            "R2": "Pbf",
            "K3": "Boc",
            "D4": "OtBu",
            "Y5": "tBu",
        }
        assert "pending" not in result.ledger.protected.values()
        assert result.errors == ()

    def test_census_rebuilds_from_residues_not_a_mutated_map(self) -> None:
        residues = (
            SequenceValidator().validate_parent_sequence(TERIPARATIDE, {}).residues
        )
        census = ProtectingGroupCensus()
        first = census.census_base(residues)
        first.ledger.protected["K13"] = "Alloc"

        rebuilt = census.census_base(residues)

        assert rebuilt.ledger.protected["K13"] == "Boc"
        assert rebuilt.ledger.protected is not first.ledger.protected

    def test_census_base_reports_unknown_residue(self) -> None:
        residues = (
            SequenceValidator()
            .validate_parent_sequence(OCTREOTIDE, {"X8": "threoninol (Thr-ol)"})
            .residues
        )
        result = ProtectingGroupCensus().census_base(residues)

        assert "X8" not in result.ledger.protected
        assert result.errors[0].code == "PROTECTING_GROUP_UNKNOWN"


class TestResinSelector(ValidationCase):
    @pytest.mark.parametrize(
        ("terminus", "family", "site", "resin"),
        [
            (
                "free_acid",
                "cyclization",
                "both termini",
                "2-chlorotrityl chloride (2-CTC)",
            ),
            (
                "free_acid",
                "c_term_amidation",
                "C-term",
                "Rink amide MBHA / ChemMatrix",
            ),
            ("amide", "n_methylation", "C2", "Rink amide MBHA / ChemMatrix"),
            ("free_acid", "lipidation", "K5", "Wang"),
        ],
    )
    def test_three_input_resin_tree(
        self, terminus: str, family: str, site: str, resin: str
    ) -> None:
        result = self.select_resin(terminus, family, site)

        assert result.selection is not None
        assert result.selection.resin == resin
        assert result.selection.route_step["stage"] == "resin_selection"
        assert result.errors == ()

    def test_alcohol_terminus_is_degraded_not_invented(self) -> None:
        result = self.select_resin("alcohol", "pegylation", "K5")

        assert result.selection is None
        assert result.errors[0].code == "RESIN_UNSUPPORTED_TERMINUS"
        assert result.errors[0].conflict_kind is None
