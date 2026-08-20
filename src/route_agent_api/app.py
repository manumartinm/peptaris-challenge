"""FastAPI application factory for the local jobs adapter."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from route_agent.observability import (
    StructuredLogger,
    bind_context,
    new_run_id,
)
from route_agent.version import package_version
from route_agent_api.cors import cors_origin_regex, cors_origins
from route_agent_api.jobs import JobStore
from route_agent_api.logging import configure_api_logging
from route_agent_api.routes import health, jobs


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    configure_api_logging()
    StructuredLogger("route_agent.api").info("api_start")
    yield
    from loguru import logger as loguru_logger

    loguru_logger.complete()


async def observability_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    incoming = request.headers.get("x-request-id") or request.headers.get("x-run-id")
    run_id = incoming.strip() if incoming and incoming.strip() else new_run_id()
    logger = StructuredLogger("route_agent.api")
    started = perf_counter()
    with bind_context(run_id=run_id, source="api"):
        logger.info(
            "http_request",
            method=request.method,
            path=request.url.path,
        )
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "http_failed",
                method=request.method,
                path=request.url.path,
                duration_ms=round((perf_counter() - started) * 1000, 3),
            )
            raise
        duration_ms = round((perf_counter() - started) * 1000, 3)
        logger.info(
            "http_response",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=duration_ms,
        )
        response.headers["X-Run-Id"] = run_id
        return response


def create_app(*, store: JobStore | None = None) -> FastAPI:
    app = FastAPI(
        title="Trace Explorer jobs", version=package_version(), lifespan=lifespan
    )
    app.state.job_store = store or JobStore()
    app.middleware("http")(observability_middleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins(),
        allow_origin_regex=cors_origin_regex(),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router, prefix="/api")
    app.include_router(jobs.router, prefix="/api")
    return app


app = create_app()
