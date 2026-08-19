from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Protocol

from route_agent.llm.calls import collect_llm_calls
from route_agent.llm.run_context import current_run, ensure_run
from route_agent.models.agent import AgentResult, CostReport, build_cost_report
from route_agent.models.conflict import ConflictTree, ValidationResult
from route_agent.models.events import EventKind, PipelineEvent, StageName
from route_agent.models.molecular import PostGraphValidationReport
from route_agent.models.request import DesignRequest
from route_agent.models.trace import PipelineTrace
from route_agent.models.verdict import RouteStep, RouteVerdict
from route_agent.observability import (
    StructuredLogger,
    bind_context,
    correlation_metadata,
    current_run_id,
    new_run_id,
)
from route_agent.observe import (
    CompositeObserver,
    LoggingObserver,
    NoOpObserver,
    PipelineObserver,
    RecordingObserver,
)
from route_agent.protocols import Tracer
from route_agent.trace import TraceWriter
from route_agent.verdict.assembler import RouteAssembler
from route_agent.verdict.route import reconstruct_route


class ValidationParser(Protocol):
    def run_validation_pipeline(self, request: DesignRequest) -> ValidationResult: ...


class ConflictWalkerLike(Protocol):
    def walk(
        self, request: DesignRequest, validation: ValidationResult
    ) -> ConflictTree: ...


class PostGraphLike(Protocol):
    def validate(
        self,
        request: DesignRequest,
        validation: ValidationResult,
        tree: ConflictTree,
    ) -> PostGraphValidationReport: ...


class FinalJudgeLike(Protocol):
    def run(
        self,
        request: DesignRequest,
        validation: ValidationResult,
        tree: ConflictTree,
        post_graph: PostGraphValidationReport,
        route_draft: tuple[RouteStep, ...],
    ) -> AgentResult: ...


@dataclass(frozen=True)
class RunResult:
    verdict: RouteVerdict
    cost: CostReport
    trace: PipelineTrace
    trace_path: Path | None = None


class RoutePipeline:
    def __init__(
        self,
        parser: ValidationParser,
        walker: ConflictWalkerLike,
        post_graph: PostGraphLike,
        judge: FinalJudgeLike,
        assembler: RouteAssembler,
        families: Any,
        traces: TraceWriter | None = None,
        logger: StructuredLogger | None = None,
        observer: PipelineObserver | None = None,
        tracer: Tracer | None = None,
    ) -> None:
        self._parser = parser
        self._walker = walker
        self._post_graph = post_graph
        self._judge = judge
        self._assembler = assembler
        self._families = families
        self._traces = traces
        self._logger = logger or StructuredLogger("route_agent.pipeline")
        self._tracer = tracer
        self._recorded = RecordingObserver()
        self._observer = CompositeObserver(
            self._recorded,
            LoggingObserver(self._logger.bind(component="route_agent.events")),
            observer or NoOpObserver(),
        )

    def run(self, request: DesignRequest) -> RunResult:
        run_id = current_run_id() or new_run_id()
        with bind_context(run_id=run_id, request_id=request.request_id):
            return self._run_traced(request, run_id)

    def _run_traced(self, request: DesignRequest, run_id: str) -> RunResult:
        started = perf_counter()
        self._logger.info("pipeline_start", **correlation_metadata())
        tracer = self._tracer
        if tracer is None:
            return self._execute(request, run_id, started)
        with ensure_run(
            tracer,
            request.request_id,
            {"node_type": "pipeline", **correlation_metadata()},
        ):
            return self._execute(request, run_id, started)

    def _execute(
        self, request: DesignRequest, run_id: str, started: float
    ) -> RunResult:
        lf_run = current_run()
        self._emit(
            "stage_started",
            "validating",
            request.request_id,
            message="validating request",
        )
        with self._span(
            lf_run, "validation_engine", {"request_id": request.request_id}
        ):
            validation = self._parser.run_validation_pipeline(request)
        self._emit(
            "stage_finished",
            "validating",
            request.request_id,
            status=validation.state.status,
        )
        self._emit(
            "stage_started",
            "walking",
            request.request_id,
            message="checking routes",
        )
        with self._span(lf_run, "walk", {"request_id": request.request_id}):
            tree = self._walker.walk(request, validation)
        self._emit(
            "stage_finished",
            "walking",
            request.request_id,
            frontier=tree.surviving_ids,
            status="pass" if tree.surviving_ids else "fail",
        )
        self._emit(
            "stage_started",
            "post_graph",
            request.request_id,
            frontier=tree.surviving_ids,
        )
        with self._span(lf_run, "post_graph", {"request_id": request.request_id}):
            post_graph = self._post_graph.validate(request, validation, tree)
        route_draft = reconstruct_route(tree, post_graph.selected_id, self._families)
        self._emit(
            "stage_finished",
            "post_graph",
            request.request_id,
            node_id=post_graph.selected_id,
        )
        self._emit(
            "stage_started",
            "judging",
            request.request_id,
            node_id=post_graph.selected_id,
        )
        with self._span(lf_run, "final_judge", {"request_id": request.request_id}):
            judge = self._judge.run(request, validation, tree, post_graph, route_draft)
        self._observer.on_event(
            PipelineEvent(
                kind="judge_finished",
                stage="judging",
                request_id=request.request_id,
                status=None
                if judge.passed is None
                else ("pass" if judge.passed else "fail"),
            )
        )
        self._emit("stage_finished", "judging", request.request_id)
        self._emit("stage_started", "assembling", request.request_id)
        verdict = self._assembler.assemble(
            request_id=request.request_id,
            validation=validation,
            tree=tree,
            post_graph=post_graph,
            families=self._families,
            judge=judge,
        )
        calls = collect_llm_calls(validation, tree, post_graph, judge)
        cost = build_cost_report(calls)
        self._observer.on_event(
            PipelineEvent(
                kind="verdict_ready",
                stage="assembling",
                request_id=request.request_id,
                message=verdict.verdict,
                calls=cost.total.calls,
                cost_usd=cost.total.cost_usd,
            )
        )
        self._emit("stage_finished", "assembling", request.request_id)
        ids = correlation_metadata()
        trace = PipelineTrace(
            request_id=request.request_id,
            run_id=ids.get("run_id"),
            job_id=ids.get("job_id"),
            request=request,
            validation=validation,
            tree=tree.to_report(
                request.request_id, extra_calls=validation.state.llm_calls
            ),
            post_graph=post_graph,
            judge=judge,
            verdict=verdict,
            cost=cost,
            llm_calls=tuple(calls),
            events=tuple(self._recorded.events),
        )
        trace_path = self._traces.write(trace) if self._traces is not None else None
        self._logger.info(
            "pipeline_complete",
            request_id=request.request_id,
            verdict=verdict.verdict,
            confidence=verdict.confidence,
            selected_id=post_graph.selected_id,
            cost_usd=cost.total.cost_usd,
            calls=cost.total.calls,
            duration_ms=round((perf_counter() - started) * 1000, 3),
            trace_path=None if trace_path is None else str(trace_path),
            status=verdict.verdict,
        )
        return RunResult(verdict=verdict, cost=cost, trace=trace, trace_path=trace_path)

    def _emit(
        self,
        kind: EventKind,
        stage: StageName,
        request_id: str,
        **kwargs: Any,
    ) -> None:
        self._observer.on_event(
            PipelineEvent(kind=kind, stage=stage, request_id=request_id, **kwargs)
        )

    @staticmethod
    def _span(run: Any, name: str, metadata: dict[str, Any]) -> Any:
        from contextlib import nullcontext

        if run is None:
            return nullcontext()
        return run.span(name, metadata)
