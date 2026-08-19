"""Parse Deep Agent graph output into AgentResult."""

from __future__ import annotations

import json
from contextlib import suppress
from typing import Any

from pydantic import ValidationError

from route_agent.llm.llm_client import (
    cost_usd_from_tokens,
    token_usage_from_exception,
    token_usage_from_graph,
)
from route_agent.models.agent import AgentObjective, AgentResult, LLMCall, ToolCall

DETAIL_LIMIT = 4000
RAW_LIMIT = 8000


class GraphOutputParser:
    def parse_agent_result(self, raw: object, objective: AgentObjective) -> AgentResult:
        if isinstance(raw, AgentResult):
            return raw.model_copy(update={"objective": objective})
        if isinstance(raw, dict):
            structured = raw.get("structured_response")
            if isinstance(structured, AgentResult):
                return structured.model_copy(update={"objective": objective})
            if isinstance(structured, dict):
                coerced = self.agent_result_from_payload(structured, objective)
                if coerced is not None:
                    return coerced
            return AgentResult(
                objective=objective,
                unknowns=("unreadable_agent_output", self.dump_graph_output(raw)),
            )
        return AgentResult(
            objective=objective,
            unknowns=("unreadable_agent_output", self.dump_graph_output(raw)),
        )

    def agent_result_from_payload(
        self, data: dict[str, Any], objective: AgentObjective
    ) -> AgentResult | None:
        cleaned = {
            key: value for key, value in data.items() if key in AgentResult.model_fields
        }
        cleaned["objective"] = objective
        try:
            return AgentResult.model_validate(cleaned)
        except ValidationError:
            return None

    def tool_args_from_message(self, message: object) -> dict[str, Any] | None:
        for call in getattr(message, "tool_calls", None) or ():
            args: object
            if isinstance(call, dict):
                args = call.get("args") or call.get("arguments")
            else:
                args = getattr(call, "args", None) or getattr(call, "arguments", None)
            if isinstance(args, str):
                with suppress(json.JSONDecodeError, TypeError, ValueError):
                    args = json.loads(args)
            if isinstance(args, dict):
                return args
        content = getattr(message, "content", None)
        if isinstance(content, str) and content.lstrip().startswith("{"):
            with suppress(json.JSONDecodeError, TypeError, ValueError):
                parsed = json.loads(content)
                if isinstance(parsed, dict):
                    return parsed
        return None

    def recover_agent_result(
        self, exc: BaseException, objective: AgentObjective
    ) -> AgentResult | None:
        message = getattr(exc, "ai_message", None)
        if message is None:
            return None
        args = self.tool_args_from_message(message)
        if args is None:
            return None
        return self.agent_result_from_payload(args, objective)

    def dump_graph_output(self, raw: object) -> str:
        if isinstance(raw, dict) and "messages" in raw:
            messages = [self.serialize_message(message) for message in raw["messages"]]
            return json.dumps({"messages": messages}, default=str)[:RAW_LIMIT]
        return json.dumps(raw, default=str)[:RAW_LIMIT]

    def serialize_message(self, message: object) -> dict[str, Any]:
        if isinstance(message, str):
            return {"content": message}
        if isinstance(message, dict):
            return message
        payload: dict[str, Any] = {"type": type(message).__name__}
        for key in ("content", "tool_calls", "additional_kwargs", "name"):
            value = getattr(message, key, None)
            if value not in (None, "", (), []):
                payload[key] = value
        return payload or {"repr": repr(message)}

    def format_exception_chain(self, exc: BaseException) -> str:
        parts = [f"{type(exc).__name__}: {exc}"]
        source = getattr(exc, "source", None)
        if source is None:
            source = exc.__cause__
        if isinstance(source, BaseException):
            parts.append(f"source: {type(source).__name__}: {source}")
            errors_fn = getattr(source, "errors", None)
            if callable(errors_fn):
                with suppress(Exception):
                    parts.append("pydantic: " + json.dumps(errors_fn(), default=str))
        return "\n".join(parts)[:DETAIL_LIMIT]

    def extract_ai_message(self, exc: BaseException) -> str | None:
        message = getattr(exc, "ai_message", None)
        if message is None:
            return None
        return json.dumps(self.serialize_message(message), default=str)[:RAW_LIMIT]

    def is_interpreter_shutdown(self, exc: BaseException) -> bool:
        if not isinstance(exc, RuntimeError):
            return False
        message = str(exc).lower()
        return "interpreter shutdown" in message or "after shutdown" in message

    def build_llm_call(
        self,
        *,
        objective: AgentObjective,
        model: str,
        raw: object = None,
        exc: BaseException | None = None,
        tool_calls: tuple[ToolCall, ...] = (),
        failed: bool = False,
    ) -> LLMCall:
        usage = token_usage_from_graph(raw)
        if usage["prompt_tokens"] == 0 and usage["completion_tokens"] == 0 and exc:
            usage = token_usage_from_exception(exc)
        input_tokens = usage["prompt_tokens"]
        output_tokens = usage["completion_tokens"]
        return LLMCall(
            call_id=f"llm_{objective}",
            model=model,
            objective=objective,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd_from_tokens(model, input_tokens, output_tokens),
            cache={"key": f"{objective}:{model}", "hit": False, "failed": failed},
            tool_calls=tool_calls,
        )

    def build_failure_result(
        self,
        objective: AgentObjective,
        exc: BaseException,
        *,
        model: str,
        tool_calls: tuple[ToolCall, ...] = (),
        raw: object = None,
    ) -> AgentResult:
        detail = self.format_exception_chain(exc)
        dumped = self.extract_ai_message(exc)
        unknowns: list[str] = [f"agent_invoke_failed:{type(exc).__name__}", detail]
        if dumped:
            unknowns.append(f"raw_output:{dumped}")
        return AgentResult(
            objective=objective,
            unknowns=tuple(unknowns),
            llm_call=self.build_llm_call(
                objective=objective,
                model=model,
                raw=raw,
                exc=exc,
                tool_calls=tool_calls,
                failed=True,
            ),
        )
