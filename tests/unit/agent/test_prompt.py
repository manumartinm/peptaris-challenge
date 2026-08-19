from __future__ import annotations

from route_agent.agent.prompt import SYSTEM_PROMPT, system_prompt_for_objective


class TestAgentPrompt:
    def test_system_prompt_forbids_verdict_and_request_edits(self) -> None:
        prompt = system_prompt_for_objective("check_compatibility")
        lowered = SYSTEM_PROMPT.lower()
        assert "never write verdict" in lowered
        assert "never edit the request" in lowered
        assert "do not call task()" in lowered
        assert "check_compatibility" in prompt
