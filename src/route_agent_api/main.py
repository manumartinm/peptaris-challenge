"""Uvicorn entrypoint for ``route-agent-api``."""

from __future__ import annotations

from route_agent_api.logging import configure_api_logging


def main() -> None:
    import uvicorn

    configure_api_logging()
    uvicorn.run(
        "route_agent_api.app:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    main()
