from __future__ import annotations

import pytest

from route_agent.llm.llm_client import (
    LlmClient,
    json_schema_response_format,
    parse_structured_response,
    token_usage_from_response,
)
from route_agent.models.request import DesignRequest
from route_agent.models.validation import StructuredFreeText
from tests.support.fake_structurer import FakeStructurer
from tests.support.validation_case import OCTREOTIDE, ValidationCase


class TestLlmClient(ValidationCase):
    def octreotide_request(self) -> DesignRequest:
        return self.request(
            request_id="REQ-05",
            parent_name="octreotide",
            sequence=OCTREOTIDE,
            parent_c_terminus="alcohol",
            residue_annotations={
                "F1": "D-Phe",
                "W4": "D-Trp",
                "X8": "threoninol (Thr-ol)",
            },
            parent_features=["disulfide C2-C7"],
            modifications=[
                {
                    "family": "pegylation",
                    "site": "K5",
                    "detail": "discrete Fmoc-PEG4, on-resin",
                }
            ],
            intent="improve solubility without disturbing the bridge",
        )

    def test_fake_structurer_extracts_embedded_site_and_occupancy(self) -> None:
        result = FakeStructurer().structure_request(self.octreotide_request())

        assert result.text.occupancy == ("disulfide",)
        assert result.text.features[0].site_token == "C2-C7"
        assert result.text.features[0].classification == "disulfide"
        assert result.errors == ()
        assert result.llm_call is None

    def test_fake_structurer_does_not_decide_chemistry_enums(self) -> None:
        result = FakeStructurer().structure_request(self.octreotide_request())

        assert all(
            feature.source_field
            in {"parent_features", "modifications.detail", "intent"}
            for feature in result.text.features
        )
        assert all(
            feature.source_field != "modifications.family"
            for feature in result.text.features
        )

    def test_disabled_client_skips_the_model(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _boom(*_args: object, **_kwargs: object) -> object:
            raise AssertionError("disabled client must not call the model")

        monkeypatch.setattr("route_agent.llm.llm_client.completion", _boom)
        result = LlmClient(enabled=False).structure_request(self.octreotide_request())

        assert result.text.features == ()
        assert result.errors == ()
        assert result.llm_call is None

    def test_client_records_retryable_error_on_model_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _boom(*_args: object, **_kwargs: object) -> object:
            raise RuntimeError("model unavailable")

        monkeypatch.setattr("route_agent.llm.llm_client.completion", _boom)
        result = LlmClient(model="openai/gpt-4o-mini").structure_request(
            self.octreotide_request()
        )

        assert result.text.features == ()
        assert result.errors[0].code == "STRUCTURER_FAILED"
        assert result.errors[0].conflict_kind is None
        assert result.errors[0].retryable is True
        assert result.llm_call is not None
        assert result.llm_call.objective == "structure_request"

    def test_emits_generation_with_input_output_under_active_run(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from tests.support.fake_tracer import FakeTracer

        text = StructuredFreeText(features=(), occupancy=("disulfide",), route_seed=())

        class Message:
            content = ""
            parsed = text

        class Choice:
            message = Message()
            finish_reason = "stop"

        class Response:
            choices = [Choice()]
            usage = {"prompt_tokens": 3, "completion_tokens": 2, "cost": 0.01}

        monkeypatch.setattr(
            "route_agent.llm.llm_client.completion", lambda **_kwargs: Response()
        )
        tracer = FakeTracer()
        with tracer.start_run("REQ-05", {"node_type": "validation"}):
            LlmClient().structure_request(self.octreotide_request())

        assert len(tracer.generations) == 1
        generation = tracer.generations[0]
        assert generation["name"] == "structure_request"
        assert generation["input"]
        assert generation["output"]["finish_reason"] == "stop"
        assert generation["usage_details"]["input"] == 3
        assert generation["cost_details"]["total"] == 0.01

    def test_invalid_json_is_structurer_invalid_output(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class Message:
            content = "not-json"

        class Choice:
            message = Message()

        class Response:
            choices = [Choice()]
            usage = {"prompt_tokens": 1, "completion_tokens": 1}

        monkeypatch.setattr(
            "route_agent.llm.llm_client.completion", lambda **_kwargs: Response()
        )
        result = LlmClient().structure_request(self.octreotide_request())

        assert result.errors[0].code == "STRUCTURER_INVALID_OUTPUT"

    def test_parsed_structured_output_is_accepted_when_content_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        text = StructuredFreeText(
            features=(), occupancy=("disulfide",), route_seed=("on_resin_modification",)
        )

        class Message:
            content = ""
            parsed = text

        class Choice:
            message = Message()
            finish_reason = "stop"

        class Response:
            choices = [Choice()]
            usage = {"input_tokens": 10, "output_tokens": 8}

        captured: dict[str, object] = {}

        def _complete(**kwargs: object) -> object:
            captured.update(kwargs)
            return Response()

        monkeypatch.setattr("route_agent.llm.llm_client.completion", _complete)
        result = LlmClient().structure_request(self.octreotide_request())

        assert result.errors == ()
        assert result.text.occupancy == ("disulfide",)
        assert result.llm_call is not None
        assert result.llm_call.output_tokens == 8
        response_format = captured["response_format"]
        assert isinstance(response_format, dict)
        assert response_format["type"] == "json_schema"
        assert captured["temperature"] == 0
        assert captured["max_tokens"] == 4096
        assert "reasoning_effort" not in captured

    def test_gpt5_terra_uses_medium_reasoning_and_completion_tokens(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, object] = {}

        def _complete(**kwargs: object) -> object:
            captured.update(kwargs)
            raise RuntimeError("stop after capturing")

        monkeypatch.setattr("route_agent.llm.llm_client.completion", _complete)
        LlmClient(model="openai/gpt-5.6-terra").structure_request(
            self.octreotide_request()
        )

        assert captured["model"] == "openai/gpt-5.6-terra"
        assert captured["reasoning_effort"] == "medium"
        assert captured["max_completion_tokens"] == 4096
        assert captured["drop_params"] is True
        assert "temperature" not in captured
        assert "max_tokens" not in captured

    def test_empty_content_and_parsed_is_structurer_invalid_output(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class Message:
            content = ""
            parsed = None
            tool_calls = ()

        class Choice:
            message = Message()
            finish_reason = "stop"

        class Response:
            choices = [Choice()]
            usage = {"prompt_tokens": 1151, "completion_tokens": 0}

        monkeypatch.setattr(
            "route_agent.llm.llm_client.completion", lambda **_kwargs: Response()
        )
        result = LlmClient().structure_request(self.octreotide_request())

        assert result.errors[0].code == "STRUCTURER_INVALID_OUTPUT"
        assert result.errors[0].input_snapshot["content_length"] == 0

    @pytest.mark.live
    def test_live_client_returns_typed_free_text(self) -> None:
        result = LlmClient().structure_request(self.octreotide_request())

        assert isinstance(result.text, StructuredFreeText)
        assert result.errors == ()
        assert any(feature.site_token == "C2-C7" for feature in result.text.features)


def _response(
    *, content: object = "", parsed: object = None, usage: object = None
) -> object:
    class Message:
        def __init__(self) -> None:
            self.content = content
            self.parsed = parsed
            self.tool_calls = ()

    class Choice:
        def __init__(self) -> None:
            self.message = Message()
            self.finish_reason = "stop"

    class Response:
        def __init__(self) -> None:
            self.choices = [Choice()]
            self.usage = usage

    return Response()


class TestStructuredOutputs:
    def test_response_format_is_unpacked_json_schema(self) -> None:
        fmt = json_schema_response_format(StructuredFreeText)

        assert fmt["type"] == "json_schema"
        assert fmt["json_schema"]["strict"] is True
        schema = fmt["json_schema"]["schema"]
        assert "$defs" not in schema
        assert schema["properties"]["features"]["type"] == "array"
        feature = schema["properties"]["features"]["items"]
        assert set(feature["required"]) == set(feature["properties"])
        assert "site_token" in feature["required"]
        assert schema["additionalProperties"] is False

    def test_parse_prefers_parsed_when_content_is_empty(self) -> None:
        parsed = StructuredFreeText(
            features=(), occupancy=("disulfide",), route_seed=()
        )
        result = parse_structured_response(
            _response(content="", parsed=parsed), StructuredFreeText
        )

        assert result.occupancy == ("disulfide",)

    def test_parse_content_json(self) -> None:
        content = (
            '{"features":[],"occupancy":["disulfide"],"route_seed":[],'
            '"unmapped_spans":[]}'
        )
        result = parse_structured_response(
            _response(content=content), StructuredFreeText
        )

        assert result.occupancy == ("disulfide",)

    def test_empty_output_raises(self) -> None:
        with pytest.raises(ValueError, match="empty structured output"):
            parse_structured_response(_response(content=""), StructuredFreeText)

    def test_usage_reads_anthropic_output_tokens(self) -> None:
        usage = token_usage_from_response(
            _response(usage={"input_tokens": 1151, "output_tokens": 42})
        )

        assert usage["prompt_tokens"] == 1151
        assert usage["completion_tokens"] == 42
