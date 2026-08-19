from __future__ import annotations

from route_agent.models.conflict import ValidationResult
from route_agent.models.request import DesignRequest
from tests.support.validation_case import ValidationCase


class TestRequestParserIntegration(ValidationCase):
    def parse_dev(self, request_id: str) -> ValidationResult:
        parser, _tracer = self.make_parser()
        request = DesignRequest.model_validate(self.design_request_row(request_id))
        return parser.run_validation_pipeline(request)

    def test_multi_disulfide_and_retro_inverso_and_amidation(self) -> None:
        disulfide = self.parse_dev("REQ-10")
        retro = self.parse_dev("REQ-11")
        amide = self.parse_dev("REQ-09")

        assert [entry.resolved for entry in disulfide.site_map] == [
            "C1",
            "C6",
            "C2",
            "C10",
            "C5",
            "C13",
        ]
        assert retro.resolved_sequence == "VPKGWRFHEMSYS"
        assert retro.site_map[0].requested == "whole sequence"
        assert amide.state.route_step is not None
        assert amide.state.route_step["resin"] == "Rink amide MBHA / ChemMatrix"
        assert amide.state.llm_calls == ()

    def test_parent_features_and_residue_annotations_survive_on_state0(
        self,
    ) -> None:
        octreotide = self.parse_dev("REQ-05")
        acetylated = self.parse_dev("REQ-02")

        assert octreotide.parent_features == ("disulfide C2-C7",)
        assert octreotide.residue_annotations == {
            "F1": "D-Phe",
            "W4": "D-Trp",
            "X8": "threoninol (Thr-ol)",
        }
        assert octreotide.parent_c_terminus == "alcohol"
        assert octreotide.intent == ("improve solubility without disturbing the bridge")
        assert octreotide.occupancy is not None
        assert octreotide.occupancy.occupancy == ("disulfide",)
        assert octreotide.occupancy.features[0].site_token == "C2-C7"
        assert octreotide.residues[0].annotation == "D-Phe"
        assert octreotide.residues[7].annotation == "threoninol (Thr-ol)"
        assert octreotide.resolved_annotations["X8"] == "threoninol (Thr-ol)"
        assert octreotide.state.output["parent_features"] == ["disulfide C2-C7"]
        assert octreotide.state.output["residue_annotations"]["F1"] == "D-Phe"
        assert octreotide.state.output["parent_c_terminus"] == "alcohol"
        assert octreotide.state.output["occupancy"] == ["disulfide"]

        assert acetylated.parent_features == ("N-terminal acetyl",)
        assert acetylated.residue_annotations["N-term"] == "acetylated in the parent"
        assert "n_terminal_cap" in acetylated.occupancy.occupancy
        assert acetylated.resolved_annotations["N-term"] == "acetylated in the parent"

    def test_branching_parent_occupancy_and_invalid_site(self) -> None:
        dual = self.parse_dev("REQ-12")
        occupied = self.parse_dev("REQ-05")
        invalid = self.make_parser()[0].run_validation_pipeline(
            DesignRequest.model_validate(
                {
                    **self.design_request_row("REQ-01"),
                    "request_id": "T-INT",
                    "modifications": [{"family": "lipidation", "site": "K99"}],
                }
            )
        )

        assert dual.state.output["protected"]["K13"] == "pending"
        assert occupied.occupancy is not None
        assert "disulfide" in occupied.occupancy.occupancy
        assert invalid.state.status == "fail"
        assert invalid.conflicts[0].kind == "site_invalid"
        assert all(
            call.objective != "check_compatibility" for call in invalid.state.llm_calls
        )

    def test_validation_result_round_trips_json(self) -> None:
        result = self.parse_dev("REQ-03")
        restored = ValidationResult.model_validate_json(result.model_dump_json())

        assert restored.request_id == "REQ-03"
        assert restored.site_map[0].requested == "V21,R25"
        assert restored.state.id == "state_0"
        assert restored.state.status == "pass"
