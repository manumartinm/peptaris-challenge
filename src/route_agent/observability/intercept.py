"""Bridge stdlib loggers (uvicorn, langchain, litellm) into Loguru."""

from __future__ import annotations

import logging

from loguru import logger


class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        logger.opt(exception=record.exc_info, depth=6).bind(component=record.name).log(
            level, record.getMessage()
        )


def intercept_stdlib(*, level: int = logging.WARNING) -> None:
    handler = InterceptHandler()
    logging.basicConfig(handlers=[handler], level=level, force=True)
    for name in (
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
        "fastapi",
        "httpx",
        "httpcore",
        "langchain",
        "langgraph",
        "liteLLM",
        "LiteLLM",
        "openai",
        "anthropic",
    ):
        std_logger = logging.getLogger(name)
        std_logger.handlers = [handler]
        std_logger.propagate = False
        std_logger.setLevel(level)
