from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from route_agent.settings import Settings
from tests.support.api import api_client, isolated_store, wait_for_job
from tests.support.cli import PUBLIC_VERDICT_FIELDS, VERDICTS
from tests.support.validation_case import ValidationCase


def _post_job(client: TestClient, payload: dict[str, Any]) -> dict[str, Any]:
    response = client.post("/api/jobs", params={"no_model": True}, json=payload)
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] in {"queued", "running"}
    return cast(dict[str, Any], body)


class TestApiJobs(ValidationCase):
    def test_health_reports_store_and_runtime(self, tmp_path: Path) -> None:
        client = api_client(isolated_store(tmp_path), Settings(no_model=True))
        response = client.get("/api/health")
        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True
        assert payload["active_job_id"] is None
        names = {item["name"] for item in payload["checks"]}
        assert {"python", "resources", "rdkit"} <= names

    def test_submit_poll_and_trace_run_pipeline(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ROUTE_AGENT_MOLECULAR_SKIP_3D", "true")
        store = isolated_store(tmp_path)
        client = api_client(store)
        accepted = _post_job(client, self.amide_acetylation_payload("T-API-INT"))
        job_id = str(accepted["job_id"])
        state = wait_for_job(client, job_id, timeout_s=60.0)
        assert state["status"] == "completed", state
        assert state["request_id"] == "T-API-INT"
        assert state["verdict"] in VERDICTS
        trace = client.get(f"/api/jobs/{job_id}/trace")
        assert trace.status_code == 200
        payload = trace.json()
        assert payload["request_id"] == "T-API-INT"
        assert set(payload["verdict"]) == PUBLIC_VERDICT_FIELDS
        listed = client.get("/api/traces")
        assert listed.status_code == 200
        ids = {item["job_id"] for item in listed.json()["traces"]}
        assert job_id in ids

    def test_pipeline_exception_marks_job_failed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class BoomPipeline:
            def run(self, request: object) -> object:
                raise RuntimeError("pipeline exploded")

        monkeypatch.setattr(
            "route_agent_api.jobs.store.build_route_pipeline",
            lambda *_args, **_kwargs: BoomPipeline(),
        )
        client = api_client(isolated_store(tmp_path))
        accepted = _post_job(client, self.amide_acetylation_payload("T-API-FAIL"))
        job_id = str(accepted["job_id"])
        state = wait_for_job(client, job_id)
        assert state["status"] == "failed"
        assert "pipeline exploded" in str(state["error"])
        trace = client.get(f"/api/jobs/{job_id}/trace")
        assert trace.status_code == 409
