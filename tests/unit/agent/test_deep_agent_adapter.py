from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from route_agent.agent.deep_agent import SKILLS_DIR, DeepAgent
from route_agent.corpus import CorpusRepository
from route_agent.literature.audit import AuditRef
from route_agent.literature.sandbox import FetchAndParse, LiteratureSandbox
from route_agent.models.agent import AgentResult
from tests.support.validation_case import ValidationCase


class FakeGraph:
    def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
        return {
            "structured_response": AgentResult(
                objective="check_compatibility", passed=True
            )
        }


class TestDeepAgent(ValidationCase):
    def test_adapter_maps_graph_output_to_agent_result(self, tmp_path: Path) -> None:
        sandbox = LiteratureSandbox(tmp_path / "research")
        agent = DeepAgent(
            graph=FakeGraph(),
            sandbox=sandbox,
            families=CorpusRepository(self.families_path),
            fetch=FetchAndParse(sandbox=sandbox),
            audit=AuditRef(sandbox=sandbox, families_path=self.families_path),
            model="fake",
        )
        result = agent.invoke(
            {
                "request_id": "REQ-01",
                "objective": "check_compatibility",
                "state": {"protected": {}},
                "candidate": {
                    "family": "lipidation",
                    "site": "K12",
                    "process": "alloc_lipidation",
                },
            }
        )

        assert result.passed is True
        assert result.objective == "check_compatibility"
        skill = tmp_path / "research" / "skills" / "check-compatibility" / "SKILL.md"
        packaged = SKILLS_DIR / "check-compatibility" / "SKILL.md"
        assert skill.is_file()
        assert skill.read_text(encoding="utf-8") == packaged.read_text(encoding="utf-8")

    def test_graph_usage_metadata_produces_nonzero_cost(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        class UsageMessage:
            usage_metadata = {"input_tokens": 100, "output_tokens": 40}

        class Graph:
            def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
                return {
                    "messages": [UsageMessage()],
                    "structured_response": AgentResult(
                        objective="check_compatibility", passed=True
                    ),
                }

        monkeypatch.setattr(
            "route_agent.agent.graph_parser.cost_usd_from_tokens",
            lambda model, input_tokens, output_tokens: 0.42,
        )
        sandbox = LiteratureSandbox(tmp_path / "research")
        agent = DeepAgent(
            graph=Graph(),
            sandbox=sandbox,
            families=CorpusRepository(self.families_path),
            fetch=FetchAndParse(sandbox=sandbox),
            audit=AuditRef(sandbox=sandbox, families_path=self.families_path),
            model="fake",
        )
        result = agent.invoke(
            {
                "request_id": "REQ-COST",
                "objective": "check_compatibility",
            }
        )

        assert result.llm_call is not None
        assert result.llm_call.input_tokens == 100
        assert result.llm_call.output_tokens == 40
        assert result.llm_call.cost_usd == 0.42
        assert result.llm_call.resolved_stage() == "walk"

    def test_structured_output_without_objective_uses_payload(
        self, tmp_path: Path
    ) -> None:
        class Graph:
            def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
                return {
                    "structured_response": {
                        "passed": False,
                        "findings": [
                            {
                                "kind": "reagent_incompatibility",
                                "description": "C-terminal amidation.",
                            }
                        ],
                    }
                }

        sandbox = LiteratureSandbox(tmp_path / "research")
        agent = DeepAgent(
            graph=Graph(),
            sandbox=sandbox,
            families=CorpusRepository(self.families_path),
            fetch=FetchAndParse(sandbox=sandbox),
            audit=AuditRef(sandbox=sandbox, families_path=self.families_path),
            model="fake",
        )
        result = agent.invoke(
            {
                "request_id": "REQ-09",
                "objective": "check_compatibility",
            }
        )

        assert result.objective == "check_compatibility"
        assert result.passed is False
        assert result.findings[0].description == "C-terminal amidation."
        assert not any(
            item.startswith("agent_invoke_failed:") for item in result.unknowns
        )

    def test_structured_output_error_missing_objective_is_recovered(
        self, tmp_path: Path
    ) -> None:
        class FakeAIMessage:
            content = ""
            tool_calls = [
                {
                    "name": "AgentResult",
                    "args": {
                        "passed": False,
                        "findings": [
                            {
                                "kind": "reagent_incompatibility",
                                "description": "C-terminal amidation.",
                            }
                        ],
                    },
                }
            ]

        class StructuredOutputValidationError(Exception):
            def __init__(self) -> None:
                self.tool_name = "AgentResult"
                self.source = ValueError("objective Field required")
                self.ai_message = FakeAIMessage()
                super().__init__(
                    "Failed to parse structured output for tool "
                    f"'{self.tool_name}': {self.source}."
                )

        class FailGraph:
            def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
                raise StructuredOutputValidationError()

        sandbox = LiteratureSandbox(tmp_path / "research")
        agent = DeepAgent(
            graph=FailGraph(),
            sandbox=sandbox,
            families=CorpusRepository(self.families_path),
            fetch=FetchAndParse(sandbox=sandbox),
            audit=AuditRef(sandbox=sandbox, families_path=self.families_path),
            model="fake",
            max_retries=0,
            base_delay=0.01,
        )
        result = agent.invoke(
            {
                "request_id": "REQ-09",
                "objective": "check_compatibility",
            }
        )

        assert result.objective == "check_compatibility"
        assert result.passed is False
        assert result.findings[0].description == "C-terminal amidation."
        assert not any(
            item.startswith("agent_invoke_failed:") for item in result.unknowns
        )

    def test_seed_skills_keeps_an_existing_tree(self, tmp_path: Path) -> None:
        sandbox = LiteratureSandbox(tmp_path / "research")
        DeepAgent(
            graph=FakeGraph(),
            sandbox=sandbox,
            families=CorpusRepository(self.families_path),
            fetch=FetchAndParse(sandbox=sandbox),
            audit=AuditRef(sandbox=sandbox, families_path=self.families_path),
            model="fake",
        )
        marker = tmp_path / "research" / "skills" / "keep.txt"
        marker.write_text("stay", encoding="utf-8")
        DeepAgent(
            graph=FakeGraph(),
            sandbox=sandbox,
            families=CorpusRepository(self.families_path),
            fetch=FetchAndParse(sandbox=sandbox),
            audit=AuditRef(sandbox=sandbox, families_path=self.families_path),
            model="fake",
        )

        assert marker.read_text(encoding="utf-8") == "stay"

    def test_tool_belt_uses_native_anthropic_web_tools(self, tmp_path: Path) -> None:
        sandbox = LiteratureSandbox(tmp_path / "research")
        agent = DeepAgent(
            graph=FakeGraph(),
            sandbox=sandbox,
            families=CorpusRepository(self.families_path),
            fetch=FetchAndParse(sandbox=sandbox),
            audit=AuditRef(sandbox=sandbox, families_path=self.families_path),
            model="fake",
        )
        belt = agent.build_tool_belt()
        native = {tool["type"]: tool for tool in belt if isinstance(tool, dict)}
        callables = {getattr(tool, "__name__", "") for tool in belt if callable(tool)}

        assert native["web_search_20250305"]["max_uses"] == 3
        assert native["web_fetch_20250910"]["max_uses"] == 2
        assert native["web_fetch_20250910"]["citations"] == {"enabled": True}
        assert "ncbi.nlm.nih.gov" in native["web_search_20250305"]["allowed_domains"]
        assert "search_literature" not in callables
        assert "fetch_and_parse" in callables
        assert "web_fetch" not in callables

    def test_openai_tool_belt_uses_responses_web_search(self, tmp_path: Path) -> None:
        sandbox = LiteratureSandbox(tmp_path / "research")
        agent = DeepAgent(
            graph=FakeGraph(),
            sandbox=sandbox,
            families=CorpusRepository(self.families_path),
            fetch=FetchAndParse(sandbox=sandbox),
            audit=AuditRef(sandbox=sandbox, families_path=self.families_path),
            model="openai/gpt-4o-mini",
        )
        belt = agent.build_tool_belt()
        native = {tool["type"]: tool for tool in belt if isinstance(tool, dict)}
        callables = {getattr(tool, "__name__", "") for tool in belt if callable(tool)}

        assert native["web_search"]["search_context_size"] == "low"
        assert "pubs.acs.org" in native["web_search"]["filters"]["allowed_domains"]
        assert "web_search_20250305" not in native
        assert "web_fetch" not in callables
        assert "fetch_and_parse" in callables
        assert "search_literature" not in callables

    def test_tool_belt_callables_have_docstrings_for_langchain(
        self, tmp_path: Path
    ) -> None:
        from langchain_core.tools import StructuredTool

        sandbox = LiteratureSandbox(tmp_path / "research")
        agent = DeepAgent(
            graph=FakeGraph(),
            sandbox=sandbox,
            families=CorpusRepository(self.families_path),
            fetch=FetchAndParse(sandbox=sandbox),
            audit=AuditRef(sandbox=sandbox, families_path=self.families_path),
            model="fake",
        )

        for tool in agent.build_tool_belt():
            if isinstance(tool, dict) or not callable(tool):
                continue
            converted = StructuredTool.from_function(tool)
            assert converted.description

    def test_fetch_and_parse_persists_web_fetch_content(self, tmp_path: Path) -> None:
        sandbox = LiteratureSandbox(tmp_path / "research")
        agent = DeepAgent(
            graph=FakeGraph(),
            sandbox=sandbox,
            families=CorpusRepository(self.families_path),
            fetch=FetchAndParse(sandbox=sandbox),
            audit=AuditRef(sandbox=sandbox, families_path=self.families_path),
            model="fake",
        )
        article = ("HATU can guanidinylate the N-terminus during slow couplings. ") * 20
        payload = agent.fetch_and_parse(
            "https://pubs.rsc.org/en/content/articlepdf/2020/md/example",
            article,
            citations=("HATU guanidinylation",),
        )

        assert payload["citeable"] is True
        assert payload["thin_content"] is False
        assert payload["full_text"] is None
        assert "HATU" in Path(payload["path"]).read_text(encoding="utf-8")

    def test_unreadable_graph_output_is_unknown(self, tmp_path: Path) -> None:
        class BadGraph:
            def invoke(self, state: dict[str, Any]) -> object:
                return {"messages": ["nope"]}

        sandbox = LiteratureSandbox(tmp_path / "research")
        agent = DeepAgent(
            graph=BadGraph(),
            sandbox=sandbox,
            families=CorpusRepository(self.families_path),
            fetch=FetchAndParse(sandbox=sandbox),
            audit=AuditRef(sandbox=sandbox, families_path=self.families_path),
            model="fake",
        )
        result = agent.invoke(
            {
                "request_id": "REQ-01",
                "objective": "check_compatibility",
            }
        )

        assert result.unknowns[0] == "unreadable_agent_output"
        assert "nope" in result.unknowns[1]

    def test_build_deep_agent_converts_litellm_model_for_langchain(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        from route_agent.agent.deep_agent import build_deep_agent
        from route_agent.agent.prompt import SYSTEM_PROMPT

        captured: dict[str, Any] = {}

        def fake_create_deep_agent(**kwargs: Any) -> object:
            captured.update(kwargs)
            return object()

        monkeypatch.setattr("deepagents.create_deep_agent", fake_create_deep_agent)
        sandbox = LiteratureSandbox(tmp_path / "research")
        build_deep_agent(
            sandbox=sandbox,
            families=CorpusRepository(self.families_path),
            fetch=FetchAndParse(sandbox=sandbox),
            audit=AuditRef(sandbox=sandbox, families_path=self.families_path),
            model="openai/gpt-4o-mini",
            system_prompt=SYSTEM_PROMPT,
            journal_allowlist=("pubs.acs.org",),
        )

        assert captured["model"] == "openai:gpt-4o-mini"
        native = {
            tool["type"]: tool for tool in captured["tools"] if isinstance(tool, dict)
        }
        assert native["web_search"]["type"] == "web_search"
        assert not captured.get("subagents")

    def test_build_deep_agent_enables_gpt5_reasoning_and_tools(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        from route_agent.agent.deep_agent import build_deep_agent
        from route_agent.agent.prompt import SYSTEM_PROMPT

        captured: dict[str, Any] = {}

        def fake_create_deep_agent(**kwargs: Any) -> object:
            captured.update(kwargs)
            return object()

        monkeypatch.setattr("deepagents.create_deep_agent", fake_create_deep_agent)
        sandbox = LiteratureSandbox(tmp_path / "research")
        build_deep_agent(
            sandbox=sandbox,
            families=CorpusRepository(self.families_path),
            fetch=FetchAndParse(sandbox=sandbox),
            audit=AuditRef(sandbox=sandbox, families_path=self.families_path),
            model="openai/gpt-5.6-terra",
            system_prompt=SYSTEM_PROMPT,
            journal_allowlist=("pubs.acs.org",),
        )

        model = captured["model"]
        name = getattr(model, "model_name", None) or getattr(model, "model", "")
        assert name == "gpt-5.6-terra"
        assert getattr(model, "reasoning_effort", None) == "medium"
        assert getattr(model, "use_responses_api", None) is True
        native = {
            tool["type"]: tool for tool in captured["tools"] if isinstance(tool, dict)
        }
        callables = {
            getattr(tool, "__name__", "")
            for tool in captured["tools"]
            if callable(tool)
        }
        assert native["web_search"]["type"] == "web_search"
        assert "family_profile_lookup" in callables
        assert "fetch_and_parse" in callables
        assert "audit_ref" in callables

    def test_invoke_caps_graph_recursion(self, tmp_path: Path) -> None:
        captured: dict[str, object] = {}

        class CaptureGraph:
            def invoke(
                self, state: dict[str, Any], config: dict[str, Any] | None = None
            ) -> dict[str, Any]:
                captured["config"] = config
                return {
                    "structured_response": AgentResult(
                        objective="check_compatibility", passed=True
                    )
                }

        sandbox = LiteratureSandbox(tmp_path / "research")
        agent = DeepAgent(
            graph=CaptureGraph(),
            sandbox=sandbox,
            families=CorpusRepository(self.families_path),
            fetch=FetchAndParse(sandbox=sandbox),
            audit=AuditRef(sandbox=sandbox, families_path=self.families_path),
            model="fake",
        )
        agent.invoke(
            {
                "request_id": "REQ-01",
                "objective": "check_compatibility",
                "candidate": {"process": "x"},
            }
        )

        assert captured["config"] == {"recursion_limit": 24}

    def test_retries_on_rate_limit_error(self, tmp_path: Path) -> None:
        attempts = []

        class RateLimitError(Exception):
            pass

        class RetryGraph:
            def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
                attempts.append(1)
                if len(attempts) < 3:
                    raise RateLimitError("rate limited")
                return {
                    "structured_response": AgentResult(
                        objective="check_compatibility", passed=True
                    )
                }

        sandbox = LiteratureSandbox(tmp_path / "research")
        agent = DeepAgent(
            graph=RetryGraph(),
            sandbox=sandbox,
            families=CorpusRepository(self.families_path),
            fetch=FetchAndParse(sandbox=sandbox),
            audit=AuditRef(sandbox=sandbox, families_path=self.families_path),
            model="fake",
            max_retries=3,
            base_delay=0.01,
        )
        result = agent.invoke(
            {
                "request_id": "REQ-01",
                "objective": "check_compatibility",
                "state": {},
                "candidate": {"family": "lipidation", "site": "K12", "process": "x"},
            }
        )

        assert len(attempts) == 3
        assert result.passed is True

    def test_invoke_emits_one_generation_per_attempt(self, tmp_path: Path) -> None:
        from tests.support.fake_tracer import FakeTracer

        sandbox = LiteratureSandbox(tmp_path / "research")
        tracer = FakeTracer()
        agent = DeepAgent(
            graph=FakeGraph(),
            sandbox=sandbox,
            families=CorpusRepository(self.families_path),
            fetch=FetchAndParse(sandbox=sandbox),
            audit=AuditRef(sandbox=sandbox, families_path=self.families_path),
            model="fake",
        )
        with tracer.start_run("REQ-GEN", {}):
            result = agent.invoke(
                {
                    "request_id": "REQ-GEN",
                    "objective": "check_compatibility",
                    "candidate": {"process": "alloc_lipidation"},
                }
            )

        assert result.passed is True
        assert len(tracer.generations) == 1
        assert tracer.generations[0]["name"] == "check_compatibility"
        assert tracer.generations[0]["metadata"]["attempt"] == 1
        assert tracer.generations[0]["model"] == "fake"

    def test_retryable_failures_emit_one_generation_per_attempt(
        self, tmp_path: Path
    ) -> None:
        from tests.support.fake_tracer import FakeTracer

        class RateLimitError(Exception):
            pass

        attempts = []

        class RetryGraph:
            def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
                attempts.append(1)
                if len(attempts) < 3:
                    raise RateLimitError("rate limited")
                return {
                    "structured_response": AgentResult(
                        objective="check_compatibility", passed=True
                    )
                }

        sandbox = LiteratureSandbox(tmp_path / "research")
        tracer = FakeTracer()
        agent = DeepAgent(
            graph=RetryGraph(),
            sandbox=sandbox,
            families=CorpusRepository(self.families_path),
            fetch=FetchAndParse(sandbox=sandbox),
            audit=AuditRef(sandbox=sandbox, families_path=self.families_path),
            model="fake",
            max_retries=3,
            base_delay=0.01,
        )
        with tracer.start_run("REQ-RETRY-GEN", {}):
            result = agent.invoke(
                {
                    "request_id": "REQ-RETRY-GEN",
                    "objective": "check_intent",
                    "candidate": {"process": "x"},
                }
            )

        assert result.passed is True
        assert len(tracer.generations) == 3
        assert tracer.generations[0]["level"] == "ERROR"
        assert tracer.generations[1]["level"] == "ERROR"
        assert "level" not in tracer.generations[2]
        assert tracer.generations[2]["name"] == "check_intent"

    def test_no_run_emits_no_generations(self, tmp_path: Path) -> None:
        from tests.support.fake_tracer import FakeTracer

        sandbox = LiteratureSandbox(tmp_path / "research")
        tracer = FakeTracer()
        agent = DeepAgent(
            graph=FakeGraph(),
            sandbox=sandbox,
            families=CorpusRepository(self.families_path),
            fetch=FetchAndParse(sandbox=sandbox),
            audit=AuditRef(sandbox=sandbox, families_path=self.families_path),
            model="fake",
        )
        agent.invoke(
            {
                "request_id": "REQ-NONE",
                "objective": "final_judge",
            }
        )
        assert tracer.generations == []

    def test_exhausted_retries_returns_agent_error(self, tmp_path: Path) -> None:
        class RateLimitError(Exception):
            pass

        class AlwaysFailGraph:
            def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
                raise RateLimitError("always fails")

        sandbox = LiteratureSandbox(tmp_path / "research")
        agent = DeepAgent(
            graph=AlwaysFailGraph(),
            sandbox=sandbox,
            families=CorpusRepository(self.families_path),
            fetch=FetchAndParse(sandbox=sandbox),
            audit=AuditRef(sandbox=sandbox, families_path=self.families_path),
            model="fake",
            max_retries=2,
            base_delay=0.01,
        )
        result = agent.invoke(
            {
                "request_id": "REQ-01",
                "objective": "check_compatibility",
            }
        )

        assert result.passed is None
        assert "agent_invoke_failed:RateLimitError" in result.unknowns
        assert any("always fails" in item for item in result.unknowns)
        assert result.llm_call is not None
        assert result.llm_call.objective == "check_compatibility"

    def test_structured_output_error_includes_model_response(
        self, tmp_path: Path
    ) -> None:
        class FakeAIMessage:
            content = "I think this is compatible."
            tool_calls = [
                {
                    "name": "AgentResult",
                    "args": {"objective": "check_compatibility", "verdict": "ok"},
                }
            ]

        class StructuredOutputValidationError(Exception):
            def __init__(self) -> None:
                self.tool_name = "AgentResult"
                self.source = ValueError("Extra inputs are not permitted [verdict]")
                self.ai_message = FakeAIMessage()
                super().__init__(
                    "Failed to parse structured output for tool "
                    f"'{self.tool_name}': {self.source}."
                )

        class FailGraph:
            def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
                raise StructuredOutputValidationError()

        sandbox = LiteratureSandbox(tmp_path / "research")
        agent = DeepAgent(
            graph=FailGraph(),
            sandbox=sandbox,
            families=CorpusRepository(self.families_path),
            fetch=FetchAndParse(sandbox=sandbox),
            audit=AuditRef(sandbox=sandbox, families_path=self.families_path),
            model="fake",
            max_retries=0,
            base_delay=0.01,
        )
        result = agent.invoke(
            {
                "request_id": "REQ-09",
                "objective": "check_compatibility",
            }
        )

        assert result.objective == "check_compatibility"
        assert result.passed is None
        assert not any(
            item.startswith("agent_invoke_failed:") for item in result.unknowns
        )
        assert result.llm_call is not None

    def test_non_retryable_error_fails_immediately(self, tmp_path: Path) -> None:
        attempts = []

        class AlwaysFailGraph:
            def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
                attempts.append(1)
                raise ValueError("not retryable")

        sandbox = LiteratureSandbox(tmp_path / "research")
        agent = DeepAgent(
            graph=AlwaysFailGraph(),
            sandbox=sandbox,
            families=CorpusRepository(self.families_path),
            fetch=FetchAndParse(sandbox=sandbox),
            audit=AuditRef(sandbox=sandbox, families_path=self.families_path),
            model="fake",
            max_retries=3,
            base_delay=0.01,
        )
        result = agent.invoke(
            {
                "request_id": "REQ-01",
                "objective": "check_compatibility",
            }
        )

        assert len(attempts) == 1
        assert "agent_invoke_failed:ValueError" in result.unknowns
        assert any("not retryable" in item for item in result.unknowns)

    def test_interpreter_shutdown_is_cancelled_without_retry(
        self, tmp_path: Path, caplog: Any, capsys: Any
    ) -> None:
        attempts = []

        class ShutdownGraph:
            def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
                attempts.append(1)
                raise RuntimeError(
                    "cannot schedule new futures after interpreter shutdown"
                )

        sandbox = LiteratureSandbox(tmp_path / "research")
        agent = DeepAgent(
            graph=ShutdownGraph(),
            sandbox=sandbox,
            families=CorpusRepository(self.families_path),
            fetch=FetchAndParse(sandbox=sandbox),
            audit=AuditRef(sandbox=sandbox, families_path=self.families_path),
            model="fake",
            max_retries=3,
            base_delay=0.01,
        )
        caplog.set_level(logging.WARNING, logger="route_agent.deep_agent")
        result = agent.invoke(
            {
                "request_id": "REQ-06",
                "objective": "check_compatibility",
                "candidate": {
                    "family": "n_methylation",
                    "site": "S11",
                    "process": "n_methylation_preferred_route",
                },
            }
        )

        assert len(attempts) == 1
        assert "agent_invoke_failed:RuntimeError" in result.unknowns
        assert "agent_invoke_cancelled" in caplog.text
        assert "agent_invoke_error" not in caplog.text
        assert "[AGENT ERROR]" not in capsys.readouterr().err
