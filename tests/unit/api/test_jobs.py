from __future__ import annotations

import threading
import time

from fastapi.testclient import TestClient

from route_agent.models.agent import AgentResult, CostReport
from route_agent.models.trace import PipelineTrace
from route_agent.models.verdict import RouteVerdict
from route_agent.observability import current_context
from route_agent.pipeline import RunResult
from route_agent_api.app import create_app
from route_agent_api.deps import get_settings, health_payload
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


def _client(store: JobStore) -> TestClient:
    return TestClient(create_app(store=store))


def _wait(client: TestClient, job_id: str) -> dict[str, object]:
    payload: dict[str, object] = {}
    for _ in range(80):
        payload = client.get(f"/api/jobs/{job_id}").json()
        if payload.get("status") in {"completed", "failed"}:
            return payload
        time.sleep(0.05)
    return payload


class TestJobsApi(ValidationCase):
    def test_submit_poll_and_trace_keep_correlation(self, monkeypatch: object) -> None:
        store = JobStore()
        captured: dict[str, object] = {}

        class FakePipeline:
            def run(self, request: object) -> RunResult:
                captured.update(current_context())
                return _result("T-API")

        monkeypatch.setattr(  # type: ignore[attr-defined]
            "route_agent_api.jobs.store.build_route_pipeline",
            lambda *_args, **_kwargs: FakePipeline(),
        )
        client = _client(store)
        response = client.post(
            "/api/jobs",
            json=self.payload(request_id="T-API"),
            headers={"X-Request-Id": "run-from-header"},
        )
        assert response.status_code == 202
        body = response.json()
        job_id = body["job_id"]
        assert body["run_id"] == "run-from-header"
        assert response.headers.get("X-Run-Id") == "run-from-header"
        state = _wait(client, job_id)
        assert state["status"] == "completed"
        assert state["run_id"] == "run-from-header"
        trace = client.get(f"/api/jobs/{job_id}/trace")
        assert trace.status_code == 200
        assert captured["job_id"] == job_id
        assert captured["request_id"] == "T-API"
        assert captured["run_id"] == "run-from-header"
        assert captured["source"] == "api"

    def test_conflict_when_another_job_is_active(self, monkeypatch: object) -> None:
        store = JobStore()
        started = threading.Event()
        release = threading.Event()

        class SlowPipeline:
            def run(self, request: object) -> RunResult:
                started.set()
                release.wait(timeout=2)
                return _result("T-BUSY")

        monkeypatch.setattr(  # type: ignore[attr-defined]
            "route_agent_api.jobs.store.build_route_pipeline",
            lambda *_args, **_kwargs: SlowPipeline(),
        )
        client = _client(store)
        first = client.post("/api/jobs", json=self.payload(request_id="T-BUSY"))
        assert first.status_code == 202
        assert started.wait(timeout=2)
        second = client.post("/api/jobs", json=self.payload(request_id="T-BUSY-2"))
        assert second.status_code == 409
        release.set()
        _wait(client, first.json()["job_id"])

    def test_trace_not_ready_is_conflict(self) -> None:
        store = JobStore()
        client = _client(store)
        missing = client.get("/api/jobs/unknown/trace")
        assert missing.status_code == 404


class TestAppFactory:
    def test_create_app_binds_store_for_health_payload(self) -> None:
        app = create_app()
        store = app.state.job_store
        assert isinstance(store, JobStore)
        payload = health_payload(store, get_settings())
        assert "checks" in payload
