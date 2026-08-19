from __future__ import annotations

import threading

from route_agent.models.agent import AgentResult, CostReport
from route_agent.models.events import PipelineEvent
from route_agent.models.trace import PipelineTrace
from route_agent.models.verdict import RouteVerdict
from route_agent.pipeline import RunResult
from route_agent_api.jobs import JobStore
from tests.support.conflict_fixtures import (
    empty_validation,
    make_tree,
    post_graph_report,
)
from tests.support.validation_case import ValidationCase


def _result(request_id: str) -> RunResult:
    request = ValidationCase().request(request_id=request_id)
    validation = empty_validation(request_id)
    tree = make_tree([], [], surviving_ids=())
    verdict = RouteVerdict(
        request_id=request_id,
        verdict="insufficient_information",
        confidence="low",
        resolved_sequence="ACDE",
        resolved_annotations={},
        site_map=validation.site_map,
        route=(),
        conflicts=(),
        unknowns=("no winning candidate",),
    )
    trace = PipelineTrace(
        request_id=request_id,
        request=request,
        validation=validation,
        tree=tree.to_report(request_id),
        post_graph=post_graph_report(request_id, selected_id=None),
        judge=AgentResult(objective="final_judge", confidence="low"),
        verdict=verdict,
        cost=CostReport(),
    )
    return RunResult(verdict=verdict, cost=CostReport(), trace=trace)


class TestJobPhases(ValidationCase):
    def test_apply_event_maps_pipeline_stages_and_progress(
        self, monkeypatch: object
    ) -> None:
        store = JobStore()
        started = threading.Event()
        release = threading.Event()

        class SlowPipeline:
            def run(self, request: object) -> RunResult:
                started.set()
                release.wait(timeout=2)
                return _result("T-PHASE")

        monkeypatch.setattr(  # type: ignore[attr-defined]
            "route_agent_api.jobs.store.build_route_pipeline",
            lambda *_args, **_kwargs: SlowPipeline(),
        )
        job = store.submit(self.request(request_id="T-PHASE"))
        assert started.wait(timeout=2)

        store.apply_event(
            job.job_id,
            PipelineEvent(
                kind="stage_finished",
                stage="validating",
                request_id="T-PHASE",
            ),
        )
        store.apply_event(
            job.job_id,
            PipelineEvent(
                kind="stage_started",
                stage="walking",
                request_id="T-PHASE",
                process="alloc_lipidation",
                site="K5",
                current=1,
                total=3,
            ),
        )
        store.apply_event(
            job.job_id,
            PipelineEvent(
                kind="molecular_validated",
                stage="post_graph",
                request_id="T-PHASE",
            ),
        )
        store.apply_event(
            job.job_id,
            PipelineEvent(
                kind="intent_checked",
                stage="post_graph",
                request_id="T-PHASE",
            ),
        )
        store.apply_event(
            job.job_id,
            PipelineEvent(
                kind="winner_selected",
                stage="post_graph",
                request_id="T-PHASE",
            ),
        )
        store.apply_event(
            job.job_id,
            PipelineEvent(
                kind="judge_finished",
                stage="judging",
                request_id="T-PHASE",
            ),
        )
        store.apply_event(
            job.job_id,
            PipelineEvent(
                kind="verdict_ready",
                stage="assembling",
                request_id="T-PHASE",
            ),
        )

        state = store.get(job.job_id)
        assert state.phase == "assemble"
        assert state.completed_phases == [
            "validate",
            "walk",
            "molecular",
            "intent",
            "judge",
            "assemble",
        ]
        assert state.progress is not None
        assert state.progress.current == 1
        assert state.progress.total == 3
        assert state.activity == "alloc_lipidation · K5"

        release.set()
