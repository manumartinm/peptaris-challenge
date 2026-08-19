from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from route_agent.settings import Settings
from route_agent_api.deps import get_settings, get_store, health_payload
from route_agent_api.jobs import JobStore

router = APIRouter()


@router.get("/health")
def health(
    store: Annotated[JobStore, Depends(get_store)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    return health_payload(store, settings)
