from __future__ import annotations

import json
import shutil
import time
import traceback
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from route_agent.agent.graph_parser import GraphOutputParser
from route_agent.agent.harness import DeepAgentHarness
from route_agent.corpus import CorpusRepository
from route_agent.literature.audit import AuditRef
from route_agent.literature.provider_tools import ProviderWebTools
from route_agent.literature.sandbox import FetchAndParse, LiteratureSandbox
from route_agent.llm.generation import trace_llm_generation
from route_agent.llm.llm_client import cost_usd_from_tokens, token_usage_from_graph
from route_agent.models.agent import AgentResult, ToolCall
from route_agent.observability import StructuredLogger, payload_fields
from route_agent.settings import DEFAULT_JOURNAL_ALLOWLIST, uses_openai_model

SKILLS_DIR = Path(__file__).resolve().parent / "skills"
SNIPPET_LIMIT = 500
DETAIL_LIMIT = 4000
RAW_LIMIT = 8000
DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY = 2.0
DEFAULT_RECURSION_LIMIT = 24
_TOOL_CALLS: ContextVar[list[ToolCall] | None] = ContextVar(
    "route_agent_tool_calls", default=None
)
_RETRYABLE_ERRORS = (
    "RateLimitError",
    "APIConnectionError",
    "Timeout",
    "StructuredOutputValidationError",
)


class DeepAgent:
    def __init__(
        self,
        sandbox: LiteratureSandbox,
        families: CorpusRepository,
        fetch: FetchAndParse,
        audit: AuditRef,
        model: str,
        journal_allowlist: tuple[str, ...] = DEFAULT_JOURNAL_ALLOWLIST,
        max_retries: int = DEFAULT_MAX_RETRIES,
        base_delay: float = DEFAULT_BASE_DELAY,
        graph: object | None = None,
    ) -> None:
        self._graph = graph
        self._sandbox = sandbox
        self._families = families
        self._fetch = fetch
        self._audit = audit
        self._model = model
        self._parser = GraphOutputParser()
        self._logger = StructuredLogger("route_agent.deep_agent")
        self._web_tools = ProviderWebTools(journal_allowlist, provider="anthropic")
        self._openai_web = ProviderWebTools(journal_allowlist, provider="openai")
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._copy_skills_into_sandbox()

    def _copy_skills_into_sandbox(self) -> None:
        """Mirror packaged skills into the sandbox mount at /skills/.

        `src/route_agent/agent/skills` is the source of truth. `research/skills`
        is a runtime copy, not a second catalog.
        """
        destination = self._sandbox.root / "skills"
        destination.mkdir(parents=True, exist_ok=True)
        for path in SKILLS_DIR.rglob("*"):
            if not path.is_file():
                continue
            target = destination / path.relative_to(SKILLS_DIR)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)

    def invoke(self, payload: dict[str, Any]) -> AgentResult:
        token = _TOOL_CALLS.set([])
        objective = payload.get("objective", "unknown")
        request_id = payload.get("request_id", "unknown")
        candidate = payload.get("candidate", {})
        try:
            raw: object | None = None
            last_exc: Exception | None = None
            for attempt in range(self._max_retries + 1):
                try:
                    with trace_llm_generation(
                        name=str(objective),
                        model=self._model,
                        metadata={
                            "attempt": attempt + 1,
                            "objective": objective,
                            "request_id": request_id,
                            "process": candidate.get("process")
                            if isinstance(candidate, dict)
                            else None,
                        },
                        input_payload=payload,
                    ) as observation:
                        try:
                            raw = self._invoke_graph_once(payload)
                        except Exception as exc:  # noqa: BLE001
                            recovered = self._parser.recover_agent_result(
                                exc, payload["objective"]
                            )
                            if recovered is not None:
                                raw = recovered
                                self._update_generation(observation, raw)
                                break
                            raise
                        self._update_generation(observation, raw)
                    break
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    if self._parser.is_interpreter_shutdown(exc):
                        self._logger.warning(
                            "agent_invoke_cancelled",
                            request=request_id,
                            objective=objective,
                            process=candidate.get("process")
                            if isinstance(candidate, dict)
                            else None,
                            error=str(exc),
                        )
                        return self._failure(payload, exc)
                    retryable = self._is_retryable_error(exc)
                    self._logger.error(
                        "agent_invoke_error",
                        request=request_id,
                        objective=objective,
                        process=candidate.get("process")
                        if isinstance(candidate, dict)
                        else None,
                        attempt=attempt + 1,
                        max_attempts=self._max_retries + 1,
                        error=type(exc).__name__,
                        retryable=retryable,
                        detail=str(exc),
                        traceback=traceback.format_exc(),
                    )
                    if not retryable or attempt >= self._max_retries:
                        return self._failure(payload, exc)
                    delay = self._base_delay * (2**attempt)
                    self._logger.info(
                        "agent_invoke_retry",
                        attempt=attempt + 1,
                        max_retries=self._max_retries,
                        delay_s=delay,
                    )
                    time.sleep(delay)
            if raw is None:
                return self._failure(
                    payload, last_exc or RuntimeError("agent invoke failed")
                )
            result = self._parser.parse_agent_result(raw, payload["objective"])
            call = self._parser.build_llm_call(
                objective=payload["objective"],
                model=self._model,
                raw=raw,
                tool_calls=tuple(_TOOL_CALLS.get() or ()),
            )
            return result.model_copy(update={"llm_call": call})
        finally:
            _TOOL_CALLS.reset(token)

    def _failure(self, payload: dict[str, Any], exc: BaseException) -> AgentResult:
        return self._parser.build_failure_result(
            payload["objective"],
            exc,
            model=self._model,
            tool_calls=tuple(_TOOL_CALLS.get() or ()),
        )

    def _invoke_graph_once(self, payload: dict[str, Any]) -> object:
        if self._graph is None:
            raise RuntimeError("deep agent graph is not bound")
        state = {
            "messages": [
                {
                    "role": "user",
                    "content": json.dumps(payload, sort_keys=True),
                }
            ]
        }
        invoke = self._graph.invoke  # type: ignore[attr-defined]
        config: dict[str, Any] = {"recursion_limit": DEFAULT_RECURSION_LIMIT}
        try:
            return invoke(state, config)
        except TypeError:
            return invoke(state)

    def _update_generation(self, observation: Any, raw: object) -> None:
        usage = token_usage_from_graph(raw)
        observation.update(
            output=self._parser.dump_graph_output(raw)
            if not isinstance(raw, AgentResult)
            else raw.model_dump(mode="json"),
            usage_details={
                "input": int(usage.get("prompt_tokens") or 0),
                "output": int(usage.get("completion_tokens") or 0),
            },
            cost_details={
                "total": cost_usd_from_tokens(
                    self._model,
                    int(usage.get("prompt_tokens") or 0),
                    int(usage.get("completion_tokens") or 0),
                )
            },
        )

    def _is_retryable_error(self, exc: Exception) -> bool:
        exc_name = type(exc).__name__
        if exc_name in _RETRYABLE_ERRORS:
            return True
        return any(parent.__name__ in _RETRYABLE_ERRORS for parent in type(exc).__mro__)

    def build_tool_belt(self) -> list[Any]:
        return [
            *self._native_web_tools_for_model(),
            self.family_profile_lookup,
            self.lookup_target,
            self.fetch_and_parse,
            self.audit_ref,
        ]

    def _native_web_tools_for_model(self) -> list[dict[str, Any]]:
        if uses_openai_model(self._model):
            return self._openai_web.native_tools()
        return self._web_tools.native_tools()

    def family_profile_lookup(self, family: str, process_id: str) -> dict[str, Any]:
        """Look up one process in extracted_families.json.

        Returns reagents, risks, alternatives, and cited excerpts for
        that family/process_id. Does not invent corpus facts.
        """
        profile = self._families.lookup_family_process(family, process_id)
        return self._record_tool_call(
            "family_profile_lookup",
            {"family": family, "process_id": process_id},
            profile.model_dump(),
        )

    def lookup_target(self, peptide: str) -> dict[str, Any]:
        """Look up a parent peptide in the ApexChem targets workbook.

        Used by check_intent. Returns availability and target fields.
        """
        result = self._families.lookup_target(peptide)
        return self._record_tool_call(
            "lookup_target", {"peptide": peptide}, result.model_dump()
        )

    def fetch_and_parse(
        self,
        url: str,
        content: str,
        citations: list[str] | tuple[str, ...] = (),
    ) -> dict[str, Any]:
        """Persist native web_fetch content as markdown under /cache/.

        Pass the URL and the text from native web_fetch. Returns a path
        and a short preview, never full text. HTML and PDF both accepted.
        """
        result = self._fetch.cache_document(url, content, citations=tuple(citations))
        payload = result.model_dump()
        if result.error:
            payload["error"] = result.error
        return self._record_tool_call(
            "fetch_and_parse",
            {"url": url, "citations": list(citations)},
            payload,
        )

    def audit_ref(self, kind: str, ref_or_source: str, basis: str) -> dict[str, Any]:
        """Verify a corpus or external citation against its source.

        kind is corpus or external. basis terms must appear in the
        cited excerpt or cached markdown.
        """
        result = self._audit.verify_citation(kind, ref_or_source, basis)
        return self._record_tool_call(
            "audit_ref",
            {"kind": kind, "ref_or_source": ref_or_source, "basis": basis},
            result.model_dump(),
        )

    def _record_tool_call(
        self, tool: str, args: dict[str, Any], payload: dict[str, Any]
    ) -> dict[str, Any]:
        snippet = json.dumps(payload, sort_keys=True, default=str)[:SNIPPET_LIMIT]
        calls = _TOOL_CALLS.get()
        if calls is None:
            calls = []
            _TOOL_CALLS.set(calls)
        calls.append(
            ToolCall(
                tool=tool,
                args=args,
                result_snippet=snippet,
                truncated=len(snippet) >= SNIPPET_LIMIT,
            )
        )
        self._logger.debug(
            "agent_tool_call",
            tool=tool,
            **payload_fields(args, key="args"),
            result_truncated=len(snippet) >= SNIPPET_LIMIT,
        )
        return payload


def build_deep_agent(
    *,
    sandbox: LiteratureSandbox,
    families: CorpusRepository,
    fetch: FetchAndParse,
    audit: AuditRef,
    model: str,
    system_prompt: str,
    journal_allowlist: tuple[str, ...],
    reasoning_effort: str = "medium",
    api_key: str | None = None,
) -> DeepAgent:
    from deepagents import create_deep_agent

    agent = DeepAgent(
        sandbox=sandbox,
        families=families,
        fetch=fetch,
        audit=audit,
        model=model,
        journal_allowlist=journal_allowlist,
    )
    harness = DeepAgentHarness(sandbox)
    harness.disable_subagent_tool(model)
    agent._graph = create_deep_agent(
        model=harness.build_chat_model(model, reasoning_effort, api_key=api_key),
        tools=agent.build_tool_belt(),
        system_prompt=system_prompt,
        skills=harness.skills(),
        memory=harness.memory(),
        permissions=harness.permissions(),
        backend=harness.backend(),
        response_format=AgentResult,
        name="route-agent",
    )
    return agent
