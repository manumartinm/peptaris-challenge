from __future__ import annotations

import pytest

from route_agent.corpus import CorpusRepository
from route_agent.models.agent import LLMCall
from route_agent.models.request import DesignRequest
from route_agent.models.validation import (
    ErrorCode,
    StructuredFreeText,
    StructuringResult,
    ValidationCheck,
    ValidationStage,
)
from route_agent.parser.errors import ErrorFactory
from route_agent.parser.request_parser import RequestParser
from tests.support.fake_structurer import FakeStructurer
from tests.support.fake_tracer import FakeTracer
from tests.support.validation_case import GLUCAGON, ValidationCase


class TestRequestParserOrchestration(ValidationCase):
    def test_valid_request_produces_pass_state0(self) -> None:
        request = self.request(
            request_id="REQ-01",
            parent_name="glucagon",
            sequence=GLUCAGON,
            modifications=[{"family": "lipidation", "site": "K12", "detail": "C18"}],
            intent="extend half-life",
        )
        parser, tracer = self.make_parser()
        result = parser.run_validation_pipeline(request)

        assert result.state.id == "state_0"
        assert result.state.status == "pass"
        assert result.state.llm_calls == ()
        assert result.resolved_sequence == request.sequence
        assert result.site_map[0].resolved == "K12"
        assert result.state.output["protected"]["K12"] == "pending"
        assert result.state.route_step is not None
        assert result.state.route_step["resin"] == "Wang"
        assert [event["name"] for event in tracer.spans] == [
            "validate_sequence",
            "validate_modification_sites",
            "parent_features",
            "resolve_family",
            "resolve_sequence",
            "assign_protecting_groups",
            "select_resin",
        ]
        assert tracer.runs[0]["request_id"] == "REQ-01"

    def test_census_and_site_map_follow_resolved_sequence(self) -> None:
        request = self.request(
            request_id="T-RESOLVED",
            parent_name="glucagon",
            sequence=GLUCAGON,
            modifications=[
                {"family": "special_residues", "site": "M27", "detail": "Met->Arg"}
            ],
        )
        result = self.make_parser()[0].run_validation_pipeline(request)

        assert result.resolved_sequence is not None
        assert result.resolved_sequence[26] == "R"
        assert result.site_map[0].requested == "M27"
        assert result.site_map[0].resolved == "R27"
        assert result.site_map[0].note is not None
        assert result.state.output["protected"]["R27"] == "Pbf"
        assert "M27" not in result.state.output["protected"]
        assert result.sites_resolved[0].atoms[0].token == "R27"

    def test_retro_inverso_remaps_pending_protection_key(self) -> None:
        request = self.request(
            request_id="T-RETRO-PG",
            parent_name="alpha-MSH",
            sequence="SYSMEHFRWGKPV",
            parent_c_terminus="amide",
            modifications=[
                {"family": "retro_inverso", "site": "whole sequence"},
                {"family": "lipidation", "site": "K11", "detail": "C16"},
            ],
        )
        result = self.make_parser()[0].run_validation_pipeline(request)
        lipid = next(entry for entry in result.site_map if entry.requested == "K11")

        assert lipid.resolved == "K3"
        assert lipid.note is not None
        assert result.state.output["protected"]["K3"] == "pending"
        assert "K11" not in result.state.output["protected"]

    def test_invalid_site_is_only_conflict_kind(self) -> None:
        request = self.request(
            request_id="T-FAIL",
            parent_name="glucagon",
            sequence=GLUCAGON,
            modifications=[{"family": "lipidation", "site": "K99"}],
        )
        result = self.make_parser()[0].run_validation_pipeline(request)

        assert result.state.status == "fail"
        assert result.conflicts[0].kind == "site_invalid"
        assert all(
            error.conflict_kind in {None, "site_invalid"}
            for error in result.state.errors
        )
        assert {error.conflict_kind for error in result.state.errors} == {
            "site_invalid"
        }

    def test_structurer_failure_degrades_without_site_invalid(self) -> None:
        class BoomStructurer:
            def structure_request(self, request: DesignRequest) -> StructuringResult:
                return StructuringResult(
                    text=StructuredFreeText(features=(), occupancy=(), route_seed=()),
                    errors=(
                        ErrorFactory().build_error(
                            code=ErrorCode.STRUCTURER_FAILED,
                            check=ValidationCheck.PARENT_FEATURES,
                            stage=ValidationStage.PARENT_FEATURES,
                            field_path="parent_features",
                            input_snapshot={"request_id": request.request_id},
                            expected="StructuredFreeText",
                            got="RuntimeError",
                            message="Grounded structurer failed: boom",
                            cause_type="structurer_failed",
                            retryable=True,
                        ),
                    ),
                    llm_call=LLMCall(
                        call_id="llm_structure_request",
                        model="test",
                        objective="structure_request",
                        input_tokens=0,
                        output_tokens=0,
                        cost_usd=0.0,
                        cache={"key": "structurer:test", "hit": False},
                    ),
                )

        parser = RequestParser(
            families=CorpusRepository(self.families_path),
            structurer=BoomStructurer(),
            tracer=FakeTracer(),
        )
        result = parser.run_validation_pipeline(
            self.request(
                request_id="T-DEG",
                parent_name="glucagon",
                sequence=GLUCAGON,
                modifications=[{"family": "lipidation", "site": "K12"}],
            )
        )

        assert result.state.status == "degraded"
        assert any(error.code == "STRUCTURER_FAILED" for error in result.state.errors)
        assert result.conflicts == ()
        assert result.state.llm_calls[0].objective == "structure_request"

    def test_business_exception_propagates_from_explicit_stage(self) -> None:
        class RaisingStructurer:
            def structure_request(self, request: DesignRequest) -> StructuringResult:
                raise RuntimeError(f"boom:{request.request_id}")

        parser = RequestParser(
            families=CorpusRepository(self.families_path),
            structurer=RaisingStructurer(),
            tracer=FakeTracer(),
        )

        with pytest.raises(RuntimeError, match="boom:T-RAISE"):
            parser.run_validation_pipeline(
                self.request(
                    request_id="T-RAISE",
                    parent_name="glucagon",
                    sequence=GLUCAGON,
                    modifications=[{"family": "lipidation", "site": "K12"}],
                )
            )

    def test_shared_error_factory_assigns_unique_ids_across_stages(self) -> None:
        parser = RequestParser(
            families=CorpusRepository(self.families_path),
            structurer=FakeStructurer(),
            tracer=FakeTracer(),
        )
        result = parser.run_validation_pipeline(
            self.request(
                request_id="T-ERR-IDS",
                sequence=GLUCAGON,
                parent_c_terminus="alcohol",
                modifications=[{"family": "lipidation", "site": "K99"}],
            )
        )
        error_ids = [error.id for error in result.state.errors]
        assert len(error_ids) >= 2
        assert error_ids == [
            f"err_{index:03d}" for index in range(1, len(error_ids) + 1)
        ]
