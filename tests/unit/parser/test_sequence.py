from __future__ import annotations

from route_agent.parser.sequence import SequenceValidator
from tests.support.validation_case import EXENATIDE, GLUCAGON, ValidationCase


class TestSequenceValidator(ValidationCase):
    def test_indexes_standard_residues_from_one(self) -> None:
        result = self.validate_sequence(self.request(sequence="ACDE"))

        assert [residue.index for residue in result.residues] == [1, 2, 3, 4]
        assert [residue.letter for residue in result.residues] == list("ACDE")
        assert result.errors == ()

    def test_attaches_declared_x_annotation(self) -> None:
        result = self.validate_sequence(
            self.request(sequence="AXC", residue_annotations={"X2": "Nle"})
        )

        assert result.residues[1].letter == "X"
        assert result.residues[1].annotation == "Nle"
        assert result.errors == ()

    def test_rejects_empty_after_construction_guard_is_bypassed_by_direct_call(
        self,
    ) -> None:
        result = SequenceValidator().validate_parent_sequence("", {})

        assert result.residues == ()
        assert result.errors[0].code == "SEQUENCE_EMPTY"
        assert result.errors[0].conflict_kind is None


class TestSequenceResolver(ValidationCase):
    def test_standard_substitution_changes_letter(self) -> None:
        result = self.resolve(
            request_id="T-RES",
            parent_name="glucagon",
            sequence=GLUCAGON,
            modifications=[
                {"family": "special_residues", "site": "M27", "detail": "Met->Arg"}
            ],
        )

        assert result.resolution.resolved_sequence[26] == "R"
        assert result.resolution.resolved_annotations == {}
        assert result.errors == ()

    def test_nonstandard_substitution_becomes_x(self) -> None:
        result = self.resolve(
            request_id="REQ-07",
            parent_name="glucagon",
            sequence=GLUCAGON,
            modifications=[
                {
                    "family": "special_residues",
                    "site": "M27",
                    "detail": "Met->Nle, oxidation-resistant surrogate",
                }
            ],
        )

        assert result.resolution.resolved_sequence == "HSQGTFTSDYSKYLDSRRAQDFVQWLXNT"
        assert result.resolution.resolved_annotations["X27"] == "Nle"

    def test_d_substitution_keeps_letter(self) -> None:
        result = self.resolve(
            request_id="REQ-04",
            parent_name="substance P",
            sequence="RPKPQQFFGLM",
            parent_c_terminus="amide",
            modifications=[
                {
                    "family": "special_residues",
                    "site": "P4",
                    "detail": "substitute D-Pro",
                }
            ],
        )

        assert result.resolution.resolved_sequence[3] == "P"
        assert result.resolution.resolved_annotations["P4"] == "D-Pro"

    def test_n_methylation_keeps_letter(self) -> None:
        result = self.resolve(
            request_id="REQ-06",
            parent_name="exenatide",
            sequence=EXENATIDE,
            parent_c_terminus="amide",
            modifications=[{"family": "n_methylation", "site": "S11"}],
        )

        assert result.resolution.resolved_sequence == EXENATIDE
        assert result.resolution.resolved_annotations == {}

    def test_retro_inverso_reverses_and_maps_indices(self) -> None:
        result = self.resolve(
            request_id="REQ-11",
            parent_name="alpha-MSH",
            sequence="SYSMEHFRWGKPV",
            parent_c_terminus="amide",
            residue_annotations={"N-term": "acetylated in the parent"},
            parent_features=["N-terminal acetyl"],
            modifications=[{"family": "retro_inverso", "site": "whole sequence"}],
        )

        assert result.resolution.resolved_sequence == "VPKGWRFHEMSYS"
        assert result.resolution.index_map[0].parent_index == 1
        assert result.resolution.index_map[0].resolved_index == 13
        assert result.resolution.resolved_annotations["V1"] == "D-Val"

    def test_two_retro_inverso_mods_restore_indices(self) -> None:
        result = self.resolve(
            request_id="T-DOUBLE-RETRO",
            parent_name="alpha-MSH",
            sequence="SYSMEHFRWGKPV",
            parent_c_terminus="amide",
            modifications=[
                {"family": "retro_inverso", "site": "whole sequence"},
                {"family": "retro_inverso", "site": "whole sequence"},
            ],
        )

        assert result.resolution.resolved_sequence == "SYSMEHFRWGKPV"
        assert result.resolution.index_map[0].parent_index == 1
        assert result.resolution.index_map[0].resolved_index == 1

    def test_invalid_retro_site_does_not_mirror_index_map(self) -> None:
        result = self.resolve(
            request_id="T-RETRO-BAD",
            parent_name="glucagon",
            sequence=GLUCAGON,
            modifications=[
                {"family": "retro_inverso", "site": "K99"},
                {"family": "special_residues", "site": "M27", "detail": "Met->Arg"},
            ],
        )

        assert result.resolution.index_map[0].resolved_index == 1
        assert result.resolution.resolved_sequence[26] == "R"

    def test_x_annotations_survive_retro(self) -> None:
        result = self.resolve(
            request_id="T-RETRO-X",
            parent_name="octreotide",
            sequence="FCFWKTCX",
            parent_c_terminus="alcohol",
            residue_annotations={"X8": "threoninol"},
            modifications=[{"family": "retro_inverso", "site": "whole sequence"}],
        )

        assert result.resolution.resolved_annotations["X1"] == "threoninol"

    def test_ambiguous_special_residue_is_internal_error(self) -> None:
        result = self.resolve(
            request_id="T-RES",
            parent_name="glucagon",
            sequence=GLUCAGON,
            modifications=[
                {
                    "family": "special_residues",
                    "site": "M27",
                    "detail": "use a suitable surrogate",
                }
            ],
        )

        assert result.resolution.resolved_sequence[26] == "M"
        assert result.errors[0].code == "SEQUENCE_TRANSFORM_AMBIGUOUS"
        assert result.errors[0].conflict_kind is None

    def test_charge_hybrid_arrow_substitutes_letter(self) -> None:
        result = self.resolve(
            request_id="T-SUB",
            parent_name="glucagon",
            sequence=GLUCAGON,
            modifications=[
                {"family": "charge_hybrids", "site": "K12", "detail": "K12->R"}
            ],
        )

        assert result.resolution.resolved_sequence[11] == "R"
        assert result.errors == ()

    def test_charge_hybrid_fmoc_arg_substitutes_letter(self) -> None:
        result = self.resolve(
            request_id="T-SUB-FMOC",
            parent_name="glucagon",
            sequence=GLUCAGON,
            modifications=[
                {
                    "family": "charge_hybrids",
                    "site": "K12",
                    "detail": "Fmoc-Arg-OH",
                }
            ],
        )

        assert result.resolution.resolved_sequence[11] == "R"
        assert result.errors == ()

    def test_charge_hybrid_unknown_bb_does_not_silent_pass(self) -> None:
        result = self.resolve(
            request_id="T-SUB-UNK",
            parent_name="glucagon",
            sequence=GLUCAGON,
            modifications=[
                {
                    "family": "charge_hybrids",
                    "site": "K12",
                    "detail": "K12->homoArg",
                }
            ],
        )

        assert result.resolution.resolved_sequence[11] == "K"
        assert result.errors[0].code == "SEQUENCE_TRANSFORM_AMBIGUOUS"
