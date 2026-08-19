"""Conflict-tree walker. CLI: `route-agent debug walk`.

`AgentResult.resolution` is advisory only; expansion uses corpus process_ids.
Degraded (`passed is None`) nodes stay on the frontier so later objectives
can still inspect them. Chemistry failures (`passed is False`) are pruned.
Timeouts and agent invocation errors are degraded but pruned from the
frontier so they are not treated as chemical impossibility.

Sibling `check_compatibility` calls at one family stage run one at a time.
A hung check is killed in a child process and marked `check_timeout`
so the walk can continue.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import networkx as nx

from route_agent.agent.failures import is_infrastructure_unknown
from route_agent.agent.runtime import AgentRuntime
from route_agent.conflict.handles import resolve_pending_handles
from route_agent.conflict.ledger import Ledger
from route_agent.corpus import CorpusRepository
from route_agent.llm.run_context import current_run
from route_agent.models.agent import AgentCandidate, AgentResult
from route_agent.models.conflict import (
    ConflictNode,
    ConflictTree,
    ProcessTrace,
    State,
    StateStatus,
    ValidationResult,
)
from route_agent.models.corpus import FamilyBinding
from route_agent.models.events import PipelineEvent, diff_state
from route_agent.models.request import DesignRequest
from route_agent.molecular.connectivity import apply_candidate_to_state
from route_agent.observability import StructuredLogger
from route_agent.observe import NoOpObserver, PipelineObserver
from route_agent.parser.sites import resolve_site_token, sites_by_modification_ref
from route_agent.process_timeout import DeadlineExceeded, run_with_deadline


@dataclass(frozen=True)
class StageOutcome:
    parent_id: str
    candidate: AgentCandidate
    result: AgentResult


class ConflictWalker:
    def __init__(
        self,
        agent: AgentRuntime,
        families: CorpusRepository,
        logger: StructuredLogger | None = None,
        check_timeout_s: float = 180.0,
        observer: PipelineObserver | None = None,
    ) -> None:
        self._agent = agent
        self._families = families
        self._logger = logger or StructuredLogger("route_agent.conflict")
        self._check_timeout_s = check_timeout_s
        self._observer = observer or NoOpObserver()

    def walk(
        self, request: DesignRequest, validation: ValidationResult
    ) -> ConflictTree:
        graph: nx.DiGraph[str] = nx.DiGraph()
        root = validation.state
        graph.add_node(
            root.id,
            node=ConflictNode(state=root, candidate=None, agent_result=None),
        )
        self._logger.info(
            "walk_start",
            request_id=request.request_id,
            root_id=root.id,
            root_status=root.status,
            families=[binding.family.value for binding in validation.family_bindings],
            check_timeout_s=self._check_timeout_s,
        )
        if root.status == "fail":
            self._logger.info("walk_skipped_failed_root", request_id=request.request_id)
            self._observer.on_event(
                PipelineEvent(
                    kind="stage_finished",
                    stage="walking",
                    request_id=request.request_id,
                    node_id=root.id,
                    status=root.status,
                    reason="failed root",
                    frontier=(),
                )
            )
            return ConflictTree(graph=graph, root_id=root.id, surviving_ids=())

        parent_c = validation.parent_c_terminus.value
        root_ledger = Ledger.seed(root.output, parent_c)
        root_ledger["sequence_snapshot"] = root.sequence_snapshot
        root_ledger["route_step"] = root.route_step
        root_ledger["building_block"] = root.building_block
        if isinstance(root.route_step, dict) and root.route_step.get("resin"):
            root_ledger["resin"] = root.route_step["resin"]
        outputs: dict[str, dict[str, Any]] = {root.id: root_ledger}
        frontier = [root.id]
        next_id = 1
        resolved_sites = self._resolved_sites_by_modification_ref(validation, request)

        for stage, binding in enumerate(validation.family_bindings, start=1):
            site = binding.site or resolved_sites[binding.modification_ref]
            candidates = self.candidates_for_site(binding, site)
            jobs = [
                (parent_id, candidate)
                for parent_id in frontier
                for candidate in candidates
            ]
            self._logger.info(
                "walk_stage_start",
                request_id=request.request_id,
                stage=stage,
                family=binding.family.value,
                modification_ref=binding.modification_ref,
                site=site,
                parents=len(frontier),
                candidates=len(candidates),
                checks=len(jobs),
            )
            outcomes = self._run_stage_checks(request, binding, outputs, jobs)
            next_frontier: list[str] = []
            for outcome in outcomes:
                child_id, keep_on_frontier = self._attach_child_node(
                    graph,
                    outputs,
                    request,
                    f"state_{next_id}",
                    binding,
                    outcome,
                )
                next_id += 1
                if keep_on_frontier:
                    next_frontier.append(child_id)
            self._observer.on_event(
                PipelineEvent(
                    kind="frontier_changed",
                    stage="walking",
                    request_id=request.request_id,
                    family=binding.family.value,
                    site=site,
                    frontier=tuple(next_frontier),
                )
            )
            self._logger.info(
                "walk_stage_done",
                request_id=request.request_id,
                stage=stage,
                family=binding.family.value,
                surviving=len(next_frontier),
                failed=len(outcomes) - len(next_frontier),
            )
            frontier = next_frontier

        self._logger.info(
            "walk_complete",
            request_id=request.request_id,
            nodes=graph.number_of_nodes(),
            surviving=len(frontier),
        )
        self._observer.on_event(
            PipelineEvent(
                kind="stage_finished",
                stage="walking",
                request_id=request.request_id,
                frontier=tuple(frontier),
            )
        )
        return ConflictTree(graph=graph, root_id=root.id, surviving_ids=tuple(frontier))

    @staticmethod
    def candidates_for_site(
        binding: FamilyBinding, site: str
    ) -> tuple[AgentCandidate, ...]:
        return tuple(
            AgentCandidate(family=binding.family.value, site=site, process=process_id)
            for process_id in binding.process_ids
        )

    def _run_stage_checks(
        self,
        request: DesignRequest,
        binding: FamilyBinding,
        outputs: dict[str, dict[str, Any]],
        jobs: list[tuple[str, AgentCandidate]],
    ) -> list[StageOutcome]:
        return [
            self._run_check_with_timeout(
                request, binding, outputs, parent_id, candidate
            )
            for parent_id, candidate in jobs
        ]

    def _run_check_with_timeout(
        self,
        request: DesignRequest,
        binding: FamilyBinding,
        outputs: dict[str, dict[str, Any]],
        parent_id: str,
        candidate: AgentCandidate,
    ) -> StageOutcome:
        self._logger.info(
            "walk_check_start",
            request_id=request.request_id,
            parent_id=parent_id,
            family=candidate.family,
            site=candidate.site,
            process=candidate.process,
            modification_ref=binding.modification_ref,
        )
        timeout = None if self._check_timeout_s <= 0 else self._check_timeout_s
        trace_context = None
        run = current_run()
        if run is not None:
            trace_context = run.trace_context()
        try:
            if timeout is None:
                result = self._invoke_compatibility_check(
                    request, outputs, parent_id, candidate, None
                )
            else:
                result = run_with_deadline(
                    self._invoke_compatibility_check,
                    (request, outputs, parent_id, candidate, trace_context),
                    timeout_s=timeout,
                )
        except DeadlineExceeded:
            self._logger.error(
                "walk_check_timeout",
                request_id=request.request_id,
                parent_id=parent_id,
                process=candidate.process,
                timeout_s=self._check_timeout_s,
            )
            return StageOutcome(
                parent_id,
                candidate,
                AgentResult(
                    objective="check_compatibility",
                    passed=None,
                    unknowns=("check_timeout",),
                ),
            )
        except Exception as exc:  # noqa: BLE001
            return StageOutcome(
                parent_id,
                candidate,
                AgentResult(
                    objective="check_compatibility",
                    passed=None,
                    unknowns=(
                        f"agent_invoke_failed:{type(exc).__name__}",
                        str(exc),
                    ),
                ),
            )
        self._logger.info(
            "walk_check_done",
            request_id=request.request_id,
            parent_id=parent_id,
            process=candidate.process,
            passed=result.passed,
            status=node_status_from_result(result),
        )
        return StageOutcome(parent_id, candidate, result)

    def _invoke_compatibility_check(
        self,
        request: DesignRequest,
        outputs: dict[str, dict[str, Any]],
        parent_id: str,
        candidate: AgentCandidate,
        trace_context: dict[str, str] | None = None,
    ) -> AgentResult:
        tracer = self._agent._tracer
        if trace_context and hasattr(tracer, "continue_span"):
            with tracer.continue_span(
                "walk.worker",
                {
                    "process": candidate.process,
                    "parent_id": parent_id,
                    "request_id": request.request_id,
                },
                trace_context,
            ):
                return self._agent.invoke(
                    "check_compatibility",
                    request,
                    outputs[parent_id],
                    candidate,
                    process_profile=self._families.lookup_family_process(
                        candidate.family, candidate.process
                    ),
                )
        return self._agent.invoke(
            "check_compatibility",
            request,
            outputs[parent_id],
            candidate,
            process_profile=self._families.lookup_family_process(
                candidate.family, candidate.process
            ),
        )

    def _attach_child_node(
        self,
        graph: nx.DiGraph[str],
        outputs: dict[str, dict[str, Any]],
        request: DesignRequest,
        child_id: str,
        binding: FamilyBinding,
        outcome: StageOutcome,
    ) -> tuple[str, bool]:
        parent_output = outputs[outcome.parent_id]
        parent_state: State = graph.nodes[outcome.parent_id]["node"].state
        status = node_status_from_result(outcome.result)
        keep_on_frontier = status == "pass" or (
            status == "degraded" and not is_infrastructure_unknown(outcome.result)
        )
        trace = ProcessTrace(
            family=outcome.candidate.family,
            site=outcome.candidate.site,
            process=outcome.candidate.process,
            modification_ref=binding.modification_ref,
            passed=outcome.result.passed,
        )
        child_out = Ledger.build_child_ledger(parent_output, trace)
        if keep_on_frontier:
            detail = None
            if 0 <= binding.modification_ref < len(request.modifications):
                detail = request.modifications[binding.modification_ref].detail
            child_out = apply_candidate_to_state(
                child_out,
                family=outcome.candidate.family,
                site=outcome.candidate.site,
                process=outcome.candidate.process,
                detail=detail,
            )
            child_out = resolve_pending_handles(child_out, outcome.candidate)
        profile = self._families.lookup_family_process(
            outcome.candidate.family, outcome.candidate.process
        )
        building_block = profile.building_blocks[0] if profile.building_blocks else None
        child = State(
            id=child_id,
            node_type="candidate",
            parents=(outcome.parent_id,),
            modification_ref=binding.modification_ref,
            status=status,
            output=child_out,
            building_block=building_block,
            sequence_snapshot=parent_state.sequence_snapshot,
            route_step=(
                {
                    "family": outcome.candidate.family,
                    "site": outcome.candidate.site,
                    "process": outcome.candidate.process,
                }
                if keep_on_frontier
                else None
            ),
            errors=(),
            provenance=(),
            llm_calls=(outcome.result.llm_call,) if outcome.result.llm_call else (),
        )
        graph.add_node(
            child_id,
            node=ConflictNode(
                state=child,
                candidate=outcome.candidate,
                agent_result=outcome.result,
            ),
        )
        graph.add_edge(outcome.parent_id, child_id)
        outputs[child_id] = child_out
        reason = None
        if outcome.result.unknowns:
            reason = outcome.result.unknowns[0]
        elif outcome.result.passed is False:
            reason = "incompatible"
        self._observer.on_event(
            PipelineEvent(
                kind="node_created" if keep_on_frontier else "branch_pruned",
                stage="walking",
                node_id=child_id,
                parent_id=outcome.parent_id,
                family=outcome.candidate.family,
                process=outcome.candidate.process,
                site=outcome.candidate.site,
                status=status,
                reason=reason,
                kept=keep_on_frontier,
                diff=diff_state(
                    parent_output,
                    child_out,
                    route_step=child.route_step
                    if isinstance(child.route_step, dict)
                    else None,
                ),
            )
        )
        self._observer.on_event(
            PipelineEvent(
                kind="candidate_evaluated",
                stage="walking",
                node_id=child_id,
                parent_id=outcome.parent_id,
                family=outcome.candidate.family,
                process=outcome.candidate.process,
                site=outcome.candidate.site,
                status=status,
                kept=keep_on_frontier,
                reason=reason,
            )
        )
        return child_id, keep_on_frontier

    def _resolved_sites_by_modification_ref(
        self, validation: ValidationResult, request: DesignRequest
    ) -> dict[int, str]:
        by_ref = sites_by_modification_ref(validation.sites_resolved)
        indexed: dict[int, str] = {}
        for modification_ref, _modification in enumerate(request.modifications):
            site = by_ref.get(modification_ref)
            if site is None:
                raise ValueError(
                    f"modification {modification_ref} has no resolved site"
                )
            indexed[modification_ref] = resolve_site_token(site)
        return indexed


def node_status_from_result(result: AgentResult) -> StateStatus:
    if is_infrastructure_unknown(result):
        return "degraded"
    if result.passed is True:
        return "pass"
    if result.passed is None:
        return "degraded"
    return "fail"
