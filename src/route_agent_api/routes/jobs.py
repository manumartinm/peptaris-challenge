from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse

from route_agent.models.request import DesignRequest
from route_agent_api.deps import get_store
from route_agent_api.jobs import (
    JobConflictError,
    JobStore,
    TraceFileError,
    TraceNotReadyError,
    UnknownJobError,
)
from route_agent_api.models import JobAccepted, JobState, StoredTraceList

router = APIRouter()


@router.post("/jobs", status_code=status.HTTP_202_ACCEPTED)
def create_job(
    request: DesignRequest,
    store: Annotated[JobStore, Depends(get_store)],
    no_model: Annotated[bool, Query()] = False,
) -> JobAccepted:
    try:
        state = store.submit(request, no_model=no_model)
    except JobConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return JobAccepted(
        job_id=state.job_id,
        status=state.status,
        request_id=state.request_id,
        run_id=state.run_id,
    )


@router.get("/traces")
def list_traces(store: Annotated[JobStore, Depends(get_store)]) -> StoredTraceList:
    return StoredTraceList(traces=store.list_stored_traces())


@router.get("/jobs/{job_id}")
def read_job(job_id: str, store: Annotated[JobStore, Depends(get_store)]) -> JobState:
    try:
        return store.get(job_id)
    except UnknownJobError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unknown job") from exc


@router.get("/jobs/{job_id}/trace")
def read_trace(
    job_id: str, store: Annotated[JobStore, Depends(get_store)]
) -> JSONResponse:
    try:
        trace = store.trace(job_id)
    except UnknownJobError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unknown job") from exc
    except TraceNotReadyError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except TraceFileError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return JSONResponse(content=trace.model_dump(mode="json"))
