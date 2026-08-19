from __future__ import annotations

import pytest
from pydantic import ValidationError

from route_agent.models.agent import LLMCall
from route_agent.models.conflict import State
from route_agent.models.corpus import Provenance
from route_agent.models.validation import ErrorCode, ValidationCheck, ValidationStage
from route_agent.models.validation import ValidationError as EngineError
from tests.support.validation_case import ValidationCase


class TestStateContracts(ValidationCase):
    def test_error_serializes_verbose_fields(self) -> None:
        error = EngineError(
            id="err_001",
            code=ErrorCode.SITE_OUT_OF_RANGE,
            check=ValidationCheck.VALIDATE_MODIFICATION_SITES,
            stage=ValidationStage.VALIDATE_MODIFICATION_SITES,
            field_path="modifications[0].site",
            input_snapshot={"site": "K99", "sequence_length": 29},
            expected="1-based index within sequence length 29",
            got="K99",
            ref=None,
            modification_ref=0,
            message="Site K99 is outside the parent sequence.",
            cause_type="site_invalid",
            retryable=False,
            conflict_kind="site_invalid",
        )

        payload = error.model_dump(mode="json")

        assert payload["code"] == "SITE_OUT_OF_RANGE"
        assert payload["check"] == "validate_modification_sites"
        assert payload["stage"] == "validate_modification_sites"
        assert payload["input_snapshot"]["site"] == "K99"
        assert payload["conflict_kind"] == "site_invalid"
        assert payload["field_path"] == "modifications[0].site"

    def test_error_rejects_unknown_code_check_or_stage(self) -> None:
        with pytest.raises(ValidationError):
            EngineError(
                id="err_001",
                code="NOT_A_CODE",  # type: ignore[arg-type]
                check=ValidationCheck.VALIDATE_SEQUENCE,
                stage=ValidationStage.VALIDATE_SEQUENCE,
                field_path="sequence",
                input_snapshot={},
                expected="enum member",
                got="NOT_A_CODE",
                ref=None,
                modification_ref=None,
                message="unknown code",
                cause_type="sequence_invalid",
                retryable=False,
            )

    def test_state_requires_llm_calls_list_and_is_frozen(self) -> None:
        state = State(
            id="state_0",
            node_type="validation",
            parents=(),
            modification_ref=None,
            status="pass",
            output={"protected": {"K12": "pending"}},
            building_block=None,
            sequence_snapshot=self.glucagon_payload()["sequence"],
            route_step={"stage": "resin_selection", "resin": "Wang"},
            errors=(),
            provenance=(
                Provenance(
                    kind="inference",
                    basis="Fmoc/tBu default side-chain policy v1",
                ),
            ),
            llm_calls=(),
        )

        dumped = state.model_dump(mode="json")
        assert dumped["llm_calls"] == []
        assert dumped["id"] == "state_0"

        with pytest.raises(ValidationError):
            state.status = "fail"

    def test_llm_call_serializes_cache_and_empty_tool_calls(self) -> None:
        call = LLMCall(
            call_id="llm_001",
            model="anthropic/claude-sonnet-4-5",
            objective="structure_request",
            input_tokens=12,
            output_tokens=8,
            cost_usd=0.0,
            cache={"key": "structurer:REQ-01", "hit": False},
            tool_calls=(),
        )

        payload = call.model_dump(mode="json")
        assert payload["objective"] == "structure_request"
        assert payload["tool_calls"] == []
        assert payload["cache"]["hit"] is False
