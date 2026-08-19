"""Reusable fake agents for walker and pipeline tests."""

from __future__ import annotations

import time
from typing import Any

from route_agent.models.agent import AgentResult, LLMCall


class ScriptedAgent:
    def __init__(self, outcomes: dict[str, bool | None] | None = None) -> None:
        self.payloads: list[dict[str, Any]] = []
        self.outcomes = outcomes or {}

    def invoke(self, payload: dict[str, Any]) -> AgentResult:
        self.payloads.append(payload)
        process = str(payload["candidate"]["process"])
        return AgentResult(
            objective=payload["objective"],
            passed=self.outcomes.get(process, True),
            llm_call=LLMCall(
                call_id="llm_check_compatibility",
                model="fake",
                objective=payload["objective"],
                input_tokens=1,
                output_tokens=1,
                cost_usd=0.0,
                cache={"key": "compat:fake", "hit": False},
            ),
        )


class SleepingOnProcessAgent(ScriptedAgent):
    def __init__(
        self,
        hang_process: str,
        outcomes: dict[str, bool | None] | None = None,
    ) -> None:
        super().__init__(outcomes)
        self.hang_process = hang_process

    def invoke(self, payload: dict[str, Any]) -> AgentResult:
        process = str(payload["candidate"]["process"])
        if process == self.hang_process:
            time.sleep(30)
        return super().invoke(payload)
