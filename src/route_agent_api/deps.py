"""Shared FastAPI dependencies. Adapters construct core objects here."""

from __future__ import annotations

from fastapi import Request

from route_agent.doctor import run_doctor
from route_agent.settings import Settings
from route_agent_api.jobs import JobStore


def get_store(request: Request) -> JobStore:
    store = request.app.state.job_store
    if not isinstance(store, JobStore):
        raise RuntimeError("job store is not configured")
    return store


def get_settings() -> Settings:
    return Settings()


def health_payload(store: JobStore, settings: Settings) -> dict[str, object]:
    report = run_doctor(settings, no_model=settings.no_model)
    payload = report.as_payload()
    payload.update(store.health())
    return payload
