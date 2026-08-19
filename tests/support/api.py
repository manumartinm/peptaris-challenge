"""HTTP helpers for the jobs API."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient

from route_agent.settings import Settings
from route_agent_api.app import create_app
from route_agent_api.deps import get_settings
from route_agent_api.jobs import JobStore


def api_client(store: JobStore, settings: Settings | None = None) -> TestClient:
    app = create_app(store=store)
    if settings is not None:
        app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def isolated_store(tmp_path: Path) -> JobStore:
    return JobStore(jobs_trace_root=tmp_path / "traces" / "jobs")


def wait_for_job(
    client: TestClient, job_id: str, *, timeout_s: float = 8.0
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    payload: dict[str, Any] = {}
    while time.monotonic() < deadline:
        payload = cast(dict[str, Any], client.get(f"/api/jobs/{job_id}").json())
        if payload.get("status") in {"completed", "failed"}:
            return payload
        time.sleep(0.05)
    return payload
