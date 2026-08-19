from __future__ import annotations

from time import perf_counter
from typing import Any

from route_agent.agent.runtime import AgentRuntime
from route_agent.llm.calls import collect_llm_calls
from route_agent.models.agent import AgentCandidate, build_cost_report
from route_agent.models.conflict import ConflictTree, ValidationResult
from route_agent.models.events import PipelineEvent
from route_agent.models.molecular import (
    CandidateMolecularValidation,
    CandidatePostGraphResult,
    PostGraphValidationReport,
)
from route_agent.models.request import DesignRequest
from route_agent.molecular.analysis import MolecularAnalyzer
from route_agent.molecular.connectivity import build_recipe
from route_agent.observability import StructuredLogger
from route_agent.observe import NoOpObserver, PipelineObserver
from route_agent.post_graph.intent import keep_intent_findings_only
from route_agent.post_graph.selector import select_winning_candidate


class PostGraphValidator:
    def __init__(
        self,
        runtime: AgentRuntime,
        molecular: MolecularAnalyzer,
        logger: StructuredLogger | None = None,
        observer: PipelineObserver | None = None,
    ) -> None:
        self._runtime = runtime
        self._molecular = molecular
        self._logger = logger or StructuredLogger("route_agent.post_graph")
        self._observer = observer or NoOpObserver()
        self._molecular.bind_logger(self._logger)

    def validate(
        self,
        request: DesignRequest,
        validation: ValidationResult,
        tree: ConflictTree,
    ) -> PostGraphValidationReport:
        jobs = list(tree.surviving_ids)
        self._logger.info(
            "post_graph_start",
            request_id=request.request_id,
            surviving=len(jobs),
            skip_3d=self._molecular.config.skip_3d,
            has_boltz_key=bool(self._molecular.config.boltz_api_key),
            boltz_timeout_s=self._molecular.config.boltz_timeout_s,
            node_ids=jobs,
        )
        if not jobs:
            self._logger.info(
                "post_graph_complete",
                request_id=request.request_id,
                selected_id=None,
            )
            return PostGraphValidationReport(
                request_id=request.request_id,
                surviving_ids=(),
                selected_id=None,
                unknowns=("no surviving candidates",),
            )

        results = [
            self._validate_node(
                request,
                validation,
                tree,
                node_id,
                current=index,
                total=len(jobs),
            )
            for index, node_id in enumerate(jobs, start=1)
        ]
        self._logger.info(
            "post_graph_select_start",
            request_id=request.request_id,
            candidates=len(results),
        )
        report = select_winning_candidate(
            request_id=request.request_id,
            surviving_ids=tree.surviving_ids,
            candidates=tuple(results),
        )
        self._observer.on_event(
            PipelineEvent(
                kind="winner_selected",
                stage="post_graph",
                request_id=request.request_id,
                node_id=report.selected_id,
                frontier=tree.surviving_ids,
            )
        )
        cost = build_cost_report(collect_llm_calls(validation, tree, report))
        report = report.model_copy(update={"cost": cost})
        self._logger.info(
            "post_graph_complete",
            request_id=request.request_id,
            selected_id=report.selected_id,
            tied=list(report.tied_ids),
            cost_usd=cost.total.cost_usd,
            calls=cost.total.calls,
        )
        return report

    def _validate_node(
        self,
        request: DesignRequest,
        validation: ValidationResult,
        tree: ConflictTree,
        node_id: str,
        *,
        current: int,
        total: int,
    ) -> CandidatePostGraphResult:
        started = perf_counter()
        node = tree.node(node_id)
        candidate = node.candidate
        self._logger.info(
            "post_graph_candidate_start",
            request_id=request.request_id,
            node_id=node_id,
            process=candidate.process if candidate else None,
            site=candidate.site if candidate else None,
            family=candidate.family if candidate else None,
        )
        recipe = build_recipe(
            node.state.output,
            sequence=validation.resolved_sequence,
            annotations=validation.resolved_annotations,
        )
        self._logger.info(
            "post_graph_recipe_done",
            node_id=node_id,
            sequence_len=len(recipe.sequence),
            fragments=len(recipe.fragments),
            n_methyl_sites=len(recipe.n_methyl_sites),
            residue_overrides=len(recipe.residue_overrides),
            unknowns=len(recipe.unknowns),
        )
        molecular = self._molecular.validate(recipe, node_id=node_id)
        self._observer.on_event(
            PipelineEvent(
                kind="molecular_validated",
                stage="post_graph",
                request_id=request.request_id,
                node_id=node_id,
                process=candidate.process if candidate else None,
                site=candidate.site if candidate else None,
                family=candidate.family if candidate else None,
                status="pass" if molecular.two_d.valid else "fail",
                reason=None if molecular.two_d.valid else "invalid_2d",
                current=current,
                total=total,
            )
        )
        intent = None
        if molecular.two_d.valid:
            self._logger.info(
                "post_graph_intent_start",
                node_id=node_id,
                formula=molecular.two_d.formula,
                exact_mw=molecular.two_d.exact_mw,
            )
            payload = dict(node.state.output)
            intent = self._runtime.invoke(
                "check_intent",
                request,
                payload,
                candidate
                or AgentCandidate(family="unknown", site="unknown", process="unknown"),
                context=_build_intent_context(request, molecular),
            )
            intent = keep_intent_findings_only(intent)
            self._logger.info(
                "post_graph_intent_done",
                node_id=node_id,
                passed=intent.passed,
                findings=len(intent.findings),
            )
        else:
            self._logger.info(
                "post_graph_intent_skipped",
                node_id=node_id,
                reason="invalid_2d",
            )
        self._observer.on_event(
            PipelineEvent(
                kind="intent_checked",
                stage="post_graph",
                request_id=request.request_id,
                node_id=node_id,
                process=candidate.process if candidate else None,
                site=candidate.site if candidate else None,
                family=candidate.family if candidate else None,
                status=None
                if intent is None or intent.passed is None
                else ("pass" if intent.passed else "fail"),
                reason=None if intent is not None else "invalid_2d",
                current=current,
                total=total,
            )
        )
        embedding_ok = (
            molecular.ensemble.embedding_ok if molecular.ensemble is not None else None
        )
        self._logger.info(
            "post_graph_candidate_done",
            request_id=request.request_id,
            node_id=node_id,
            valid_2d=molecular.two_d.valid,
            intent_passed=None if intent is None else intent.passed,
            embedding_ok=embedding_ok,
            duration_ms=_ms(started),
            unknowns=len(molecular.unknowns),
        )
        return CandidatePostGraphResult(
            node_id=node_id,
            candidate=candidate,
            molecular=molecular,
            intent=intent,
        )


def _ms(started: float) -> int:
    return int((perf_counter() - started) * 1000)


def _build_intent_context(
    request: DesignRequest, molecular: CandidateMolecularValidation
) -> dict[str, Any]:
    descriptors = (
        molecular.descriptors.model_dump(mode="json") if molecular.descriptors else {}
    )
    ensemble = None
    if molecular.ensemble is not None:
        ensemble = molecular.ensemble.model_dump(mode="json")
        ensemble.pop("sdf", None)
        ensemble.pop("cif", None)
    return {
        "parent_peptide": request.parent_name,
        "resolved_sequence": molecular.recipe.sequence if molecular.recipe else None,
        "molecular_validation": {
            "valid": molecular.two_d.valid,
            "formula": molecular.two_d.formula,
            "exact_mw": molecular.two_d.exact_mw,
            **descriptors,
        },
        "ensemble_3d": ensemble,
        "recipe": molecular.recipe.model_dump(mode="json")
        if molecular.recipe
        else None,
    }
