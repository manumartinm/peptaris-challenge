from __future__ import annotations

from collections import OrderedDict
from time import perf_counter
from typing import Any

from route_agent.agent.prompt import system_prompt_for_objective
from route_agent.agent.state_categories import derive_state_categories
from route_agent.corpus import CorpusRepository
from route_agent.literature.sandbox import LiteratureSandbox
from route_agent.llm.run_context import ensure_run
from route_agent.models.agent import (
    AgentCandidate,
    AgentObjective,
    AgentResult,
    LLMCall,
    ProcessProfile,
)
from route_agent.models.corpus import TargetLookupResult
from route_agent.models.request import DesignRequest
from route_agent.observability import StructuredLogger
from route_agent.protocols import DeepAgent, Tracer

DEFAULT_MAX_ENTRIES = 256


class CompatCache:
    """Per-request compatibility cache. Not shared across requests."""

    def __init__(self, max_entries: int = DEFAULT_MAX_ENTRIES) -> None:
        self._store: OrderedDict[tuple[str, str, frozenset[str]], AgentResult] = (
            OrderedDict()
        )
        self._max_entries = max_entries

    def state_categories_present(self, state_payload: dict[str, Any]) -> frozenset[str]:
        return derive_state_categories(state_payload)

    def lookup(
        self, process_id: str, site: str, state_payload: dict[str, Any]
    ) -> AgentResult | None:
        key = (process_id, site, self.state_categories_present(state_payload))
        result = self._store.get(key)
        if result is not None:
            self._store.move_to_end(key)
        return result

    def store(
        self,
        process_id: str,
        site: str,
        state_payload: dict[str, Any],
        result: AgentResult,
    ) -> None:
        key = (process_id, site, self.state_categories_present(state_payload))
        self._store[key] = result
        self._store.move_to_end(key)
        while len(self._store) > self._max_entries:
            self._store.popitem(last=False)


def build_prior_payload(
    state_payload: dict[str, Any], request: DesignRequest
) -> dict[str, Any]:
    route_step = state_payload.get("route_step")
    resin = state_payload.get("resin")
    if resin is None and isinstance(route_step, dict):
        resin = route_step.get("resin")
    return {
        "sequence_snapshot": state_payload.get("sequence_snapshot") or request.sequence,
        "resin": resin,
        "route_step": route_step,
        "parent_c_terminus": request.parent_c_terminus.value,
        "history": list(state_payload.get("history") or []),
    }


class AgentRuntime:
    def __init__(
        self,
        sandbox: LiteratureSandbox,
        tracer: Tracer,
        logger: StructuredLogger,
        cache: CompatCache,
        agent: DeepAgent | None = None,
        enabled: bool = True,
        model: str = "anthropic/claude-sonnet-4-5",
        families: CorpusRepository | None = None,
    ) -> None:
        self._sandbox = sandbox
        self._tracer = tracer
        self._agent = agent
        self._enabled = enabled
        self._model = model
        self._logger = logger
        self._cache = cache
        self._families = families
        self._written_prompts: set[tuple[str, AgentObjective]] = set()

    def invoke(
        self,
        objective: AgentObjective,
        request: DesignRequest,
        state_payload: dict[str, Any],
        candidate: AgentCandidate,
        process_profile: ProcessProfile | dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> AgentResult:
        if not self._enabled or self._agent is None:
            return AgentResult(
                objective=objective,
                unknowns=("model disabled",),
            )
        if objective == "check_compatibility":
            cached = self._cache.lookup(
                candidate.process, candidate.site, state_payload
            )
            if cached is not None:
                self._logger.info(
                    "agent_cache_hit",
                    request_id=request.request_id,
                    objective=objective,
                    process=candidate.process,
                )
                return self._mark_cache_hit(cached)
        prompt = system_prompt_for_objective(objective)
        payload = {
            "request_id": request.request_id,
            "objective": objective,
            "system_prompt": prompt,
            "state": state_payload,
            "candidate": candidate.model_dump(mode="json"),
            "intent": request.intent,
            "prior": build_prior_payload(state_payload, request),
            "process_profile": self._process_profile_payload(
                candidate, process_profile
            ),
            "parent_target": self._lookup_parent_target(request.parent_name),
        }
        if objective == "check_intent":
            payload.setdefault("parent_peptide", request.parent_name)
            payload.setdefault(
                "resolved_sequence",
                state_payload.get("resolved_sequence") or request.sequence,
            )
            payload.setdefault("candidate_process", candidate.process)
        if context:
            payload.update(context)
        self._write_system_prompt_once(request.request_id, objective, prompt)
        started = perf_counter()
        metadata = {
            "request_id": request.request_id,
            "objective": objective,
            "process": candidate.process,
        }
        with (
            ensure_run(
                self._tracer,
                request.request_id,
                {"node_type": "agent", "objective": objective},
            ) as run,
            run.span(f"agent/{objective}", metadata),
        ):
            result = self._agent.invoke(payload)
        if objective == "check_compatibility":
            self._cache.store(candidate.process, candidate.site, state_payload, result)
        self._logger.info(
            "agent_complete",
            request_id=request.request_id,
            objective=objective,
            process=candidate.process,
            passed=result.passed,
            duration_ms=round((perf_counter() - started) * 1000, 3),
            cache_hit=False,
        )
        return result

    def _process_profile_payload(
        self,
        candidate: AgentCandidate,
        process_profile: ProcessProfile | dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if isinstance(process_profile, ProcessProfile):
            return process_profile.model_dump(mode="json")
        if isinstance(process_profile, dict):
            return process_profile
        if self._families is None:
            return None
        return self._families.lookup_family_process(
            candidate.family, candidate.process
        ).model_dump(mode="json")

    def _lookup_parent_target(self, parent_name: str) -> dict[str, Any]:
        if self._families is None:
            return TargetLookupResult.unavailable(parent_name).model_dump(mode="json")
        return self._families.lookup_target(parent_name).model_dump(mode="json")

    def _write_system_prompt_once(
        self, request_id: str, objective: AgentObjective, prompt: str
    ) -> None:
        key = (request_id, objective)
        if key in self._written_prompts:
            return
        self._sandbox.write_memory(request_id, "AGENTS.md", prompt)
        if not (self._sandbox.memory_dir / "AGENTS.md").is_file():
            self._sandbox.write_shared_memory("AGENTS.md", prompt)
        self._written_prompts.add(key)

    def _mark_cache_hit(self, result: AgentResult) -> AgentResult:
        call = result.llm_call
        if call is None:
            call = LLMCall(
                call_id="llm_check_compatibility",
                model=self._model,
                objective="check_compatibility",
                input_tokens=0,
                output_tokens=0,
                cost_usd=0.0,
                cache={"key": "compat", "hit": True},
            )
        else:
            call = call.model_copy(
                update={
                    "cache": {**call.cache, "hit": True},
                    "cost_usd": 0.0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                }
            )
        return result.model_copy(update={"llm_call": call})
