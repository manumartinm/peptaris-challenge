"""Uvicorn entrypoint for ``route-agent-api``."""

from __future__ import annotations

from route_agent_api.bind import listen_host, listen_port
from route_agent_api.logging import configure_api_logging


def main() -> None:
    import uvicorn

    configure_api_logging()
    uvicorn.run(
        "route_agent_api.app:app",
        host=listen_host(),
        port=listen_port(),
        reload=False,
    )


if __name__ == "__main__":
    main()
