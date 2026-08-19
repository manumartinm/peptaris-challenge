from __future__ import annotations

import json
from collections.abc import Iterable
from time import perf_counter
from typing import Any

from litellm import completion
from pydantic import BaseModel

from route_agent.llm.generation import trace_llm_generation
from route_agent.models.agent import LLMCall
from route_agent.models.request import DesignRequest
from route_agent.models.validation import (
    ErrorCode,
    StructuredFreeText,
    StructuringResult,
    ValidationCheck,
    ValidationStage,
)
from route_agent.observability import StructuredLogger
from route_agent.parser.errors import ErrorFactory
from route_agent.settings import uses_gpt5_reasoning_model

SYSTEM_PROMPT = """You are a grounded structurer for peptide design requests.

Classify free text only. You must NOT:
- decide whether a site is valid
- perform index arithmetic
- choose or change family enums
- assign protecting groups
- choose a resin
- invent chemistry that is not in the text

Inputs are parent_features, modifications[].detail, and intent.
For each string, classify it, and extract an embedded site token only if it
appears verbatim (K12, C2-C7, N-term, C-term, both termini, whole sequence).
Provide character spans as evidence. Put leftover unclassified fragments in
unmapped_spans. Occupancy is parent chemistry already present. Route_seed is
synthesis-context hints from details, not a route.

Return only StructuredFreeText. features, occupancy, and route_seed
may be empty arrays when the text has nothing to classify.
"""


def json_schema_response_format(model: type[BaseModel]) -> dict[str, Any]:
    from openai.lib._pydantic import to_strict_json_schema

    schema = to_strict_json_schema(model)
    defs = schema.pop("$defs", schema.pop("definitions", {}))
    if defs:
        from litellm.litellm_core_utils.prompt_templates.common_utils import (
            unpack_defs,
        )

        unpack_defs(schema, defs)
    schema.pop("title", None)
    return {
        "type": "json_schema",
        "json_schema": {
            "name": model.__name__,
            "strict": True,
            "schema": schema,
        },
    }


def token_usage_from_response(response: Any) -> dict[str, Any]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return {}
    if isinstance(usage, dict):
        payload = dict(usage)
    else:
        payload = {
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
            "input_tokens": getattr(usage, "input_tokens", None),
            "output_tokens": getattr(usage, "output_tokens", None),
            "cost": getattr(usage, "cost", None),
            "total_cost": getattr(usage, "total_cost", None),
        }
    prompt = payload.get("prompt_tokens") or payload.get("input_tokens") or 0
    completion = payload.get("completion_tokens") or payload.get("output_tokens") or 0
    payload["prompt_tokens"] = int(prompt)
    payload["completion_tokens"] = int(completion)
    return payload


def token_usage_from_messages(messages: Iterable[object] | None) -> dict[str, int]:
    prompt = 0
    completion = 0
    for message in messages or ():
        usage = getattr(message, "usage_metadata", None)
        if usage is None and isinstance(message, dict):
            usage = message.get("usage_metadata") or message.get("usage")
        if usage is None:
            continue
        if isinstance(usage, dict):
            prompt += int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
            completion += int(
                usage.get("output_tokens") or usage.get("completion_tokens") or 0
            )
        else:
            prompt += int(
                getattr(usage, "input_tokens", 0)
                or getattr(usage, "prompt_tokens", 0)
                or 0
            )
            completion += int(
                getattr(usage, "output_tokens", 0)
                or getattr(usage, "completion_tokens", 0)
                or 0
            )
    return {"prompt_tokens": prompt, "completion_tokens": completion}


def token_usage_from_graph(raw: object) -> dict[str, int]:
    if isinstance(raw, dict) and raw.get("messages") is not None:
        return token_usage_from_messages(raw["messages"])
    return {"prompt_tokens": 0, "completion_tokens": 0}


def token_usage_from_exception(exc: BaseException) -> dict[str, int]:
    message = getattr(exc, "ai_message", None)
    if message is None:
        return {"prompt_tokens": 0, "completion_tokens": 0}
    return token_usage_from_messages((message,))


def cost_usd_from_tokens(model: str, input_tokens: int, output_tokens: int) -> float:
    if input_tokens <= 0 and output_tokens <= 0:
        return 0.0
    try:
        from litellm import cost_per_token

        prompt_cost, completion_cost = cost_per_token(
            model=model,
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
        )
    except Exception:  # noqa: BLE001
        return 0.0
    return float(prompt_cost) + float(completion_cost)


def parse_structured_response[T: BaseModel](response: Any, model: type[T]) -> T:
    message = response.choices[0].message
    parsed = getattr(message, "parsed", None)
    if isinstance(parsed, model):
        return parsed
    if isinstance(parsed, dict):
        return model.model_validate(parsed)
    raw = _json_payload_from_message(message)
    if not raw:
        raise ValueError("empty structured output")
    return model.model_validate_json(raw)


def message_content_as_text(message: Any) -> str:
    content = getattr(message, "content", None)
    if isinstance(content, list):
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    if isinstance(content, str):
        return content
    return str(content or "")


def _json_payload_from_message(message: Any) -> str:
    text = message_content_as_text(message)
    if text:
        return text
    tool_calls = getattr(message, "tool_calls", None) or ()
    if tool_calls:
        first = tool_calls[0]
        function = getattr(first, "function", first)
        arguments = getattr(function, "arguments", None)
        if isinstance(arguments, dict):
            return json.dumps(arguments)
        if arguments:
            return str(arguments)
    return ""


class LlmClient:
    def __init__(
        self,
        model: str = "anthropic/claude-sonnet-4-5",
        errors: ErrorFactory | None = None,
        enabled: bool = True,
        api_key: str | None = None,
        timeout: float = 60.0,
        max_retries: int = 2,
        reasoning_effort: str = "medium",
    ) -> None:
        self._model = model
        self._errors = errors or ErrorFactory()
        self._enabled = enabled
        self._api_key = api_key
        self._timeout = timeout
        self._max_retries = max_retries
        self._reasoning_effort = reasoning_effort
        self._logger = StructuredLogger("route_agent.llm")

    def structure_request(self, request: DesignRequest) -> StructuringResult:
        if not self._enabled:
            return StructuringResult(
                text=StructuredFreeText(features=(), occupancy=(), route_seed=()),
                errors=(),
                llm_call=None,
            )
        payload = {
            "request_id": request.request_id,
            "parent_features": list(request.parent_features),
            "modification_details": [
                {"index": index, "detail": modification.detail}
                for index, modification in enumerate(request.modifications)
            ],
            "intent": request.intent,
        }
        try:
            response = self._call_completion_with_retries(payload)
        except Exception as exc:  # noqa: BLE001 - surface any provider failure
            return self._failed_structuring(
                code=ErrorCode.STRUCTURER_FAILED,
                expected="StructuredFreeText",
                got=type(exc).__name__,
                message=f"Grounded structurer failed: {exc}",
                snapshot={"request_id": request.request_id},
                usage={},
                failed=True,
            )

        usage = token_usage_from_response(response)
        try:
            text = parse_structured_response(response, StructuredFreeText)
        except Exception as exc:  # noqa: BLE001
            content = message_content_as_text(response.choices[0].message)
            return self._failed_structuring(
                code=ErrorCode.STRUCTURER_INVALID_OUTPUT,
                expected="StructuredFreeText JSON",
                got=type(exc).__name__,
                message=f"Structurer output was not valid StructuredFreeText: {exc}",
                snapshot={
                    "content_length": len(content),
                    "finish_reason": getattr(
                        response.choices[0], "finish_reason", None
                    ),
                },
                usage=usage,
            )
        return StructuringResult(
            text=text,
            errors=(),
            llm_call=self._build_llm_call_record(usage=usage),
        )

    def _build_llm_call_record(
        self, usage: dict[str, Any], failed: bool = False
    ) -> LLMCall:
        return LLMCall(
            call_id="llm_structure_request",
            model=self._model,
            objective="structure_request",
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            cost_usd=self._cost_usd_from_usage(usage),
            cache={"key": f"structurer:{self._model}", "hit": False, "failed": failed},
            tool_calls=(),
            stage="validate",
        )

    def _failed_structuring(
        self,
        *,
        code: ErrorCode,
        expected: str,
        got: str,
        message: str,
        snapshot: dict[str, Any],
        usage: dict[str, Any],
        failed: bool = False,
    ) -> StructuringResult:
        return StructuringResult(
            text=StructuredFreeText(features=(), occupancy=(), route_seed=()),
            errors=(
                self._errors.build_error(
                    code=code,
                    check=ValidationCheck.PARENT_FEATURES,
                    stage=ValidationStage.PARENT_FEATURES,
                    field_path="parent_features",
                    input_snapshot=snapshot,
                    expected=expected,
                    got=got,
                    message=message,
                    cause_type="structurer_failed",
                    retryable=True,
                ),
            ),
            llm_call=self._build_llm_call_record(usage=usage, failed=failed),
        )

    def _call_completion_with_retries(self, payload: dict[str, Any]) -> Any:
        kwargs = self._build_completion_kwargs(payload)
        last_error: Exception | None = None
        attempts = max(1, self._max_retries + 1)
        messages = kwargs.get("messages")
        for attempt in range(attempts):
            started = perf_counter()
            try:
                with trace_llm_generation(
                    name="structure_request",
                    model=self._model,
                    metadata={
                        "attempt": attempt + 1,
                        "objective": "structure_request",
                    },
                    input_payload=messages,
                ) as observation:
                    response = completion(**kwargs)
                    usage = token_usage_from_response(response)
                    duration_ms = round((perf_counter() - started) * 1000, 3)
                    observation.update(
                        output=_generation_output(response),
                        usage_details={
                            "input": int(usage.get("prompt_tokens") or 0),
                            "output": int(usage.get("completion_tokens") or 0),
                        },
                        cost_details={"total": self._cost_usd_from_usage(usage)},
                        metadata={
                            "duration_ms": duration_ms,
                            "attempt": attempt + 1,
                        },
                    )
                    self._log_generation(
                        attempt=attempt + 1,
                        usage=usage,
                        duration_ms=duration_ms,
                    )
                    return response
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                self._logger.warning(
                    "llm_generation",
                    model=self._model,
                    attempt=attempt + 1,
                    duration_ms=round((perf_counter() - started) * 1000, 3),
                    status="error",
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
        assert last_error is not None
        raise last_error

    def _log_generation(
        self, *, attempt: int, usage: dict[str, Any], duration_ms: float
    ) -> None:
        self._logger.info(
            "llm_generation",
            model=self._model,
            attempt=attempt,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            cost_usd=self._cost_usd_from_usage(usage),
            duration_ms=duration_ms,
            status="ok",
        )

    def _build_completion_kwargs(self, payload: dict[str, Any]) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, sort_keys=True)},
            ],
            "response_format": json_schema_response_format(StructuredFreeText),
            "timeout": self._timeout,
        }
        if uses_gpt5_reasoning_model(self._model):
            kwargs["max_completion_tokens"] = 4096
            kwargs["reasoning_effort"] = self._reasoning_effort
            kwargs["drop_params"] = True
        else:
            kwargs["temperature"] = 0
            kwargs["max_tokens"] = 4096
        if self._api_key is not None:
            kwargs["api_key"] = self._api_key
        return kwargs

    def _cost_usd_from_usage(self, usage: dict[str, Any]) -> float:
        raw = usage.get("cost") or usage.get("total_cost")
        return float(raw) if raw is not None else 0.0


def _generation_output(response: Any) -> dict[str, Any]:
    choice = response.choices[0]
    message = choice.message
    return {
        "content": message_content_as_text(message),
        "finish_reason": getattr(choice, "finish_reason", None),
    }
