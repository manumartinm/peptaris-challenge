"""Filesystem harness for the Deep Agent sandbox. No shell access."""

from __future__ import annotations

from typing import Any

from deepagents import (
    FilesystemPermission,
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    register_harness_profile,
)
from deepagents.backends import CompositeBackend, FilesystemBackend

from route_agent.literature.sandbox import LiteratureSandbox
from route_agent.settings import (
    langchain_model_spec,
    uses_gpt5_reasoning_model,
)


class DeepAgentHarness:
    def __init__(self, sandbox: LiteratureSandbox) -> None:
        self._sandbox = sandbox
        (sandbox.root / "skills").mkdir(parents=True, exist_ok=True)

    def backend(self) -> CompositeBackend:
        workspace = self._sandbox.root / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        files = FilesystemBackend(root_dir=workspace, virtual_mode=True)
        return CompositeBackend(
            default=files,
            routes={
                "/cache/": FilesystemBackend(
                    root_dir=self._sandbox.cache_dir, virtual_mode=True
                ),
                "/memory/": FilesystemBackend(
                    root_dir=self._sandbox.memory_dir, virtual_mode=True
                ),
                "/skills/": FilesystemBackend(
                    root_dir=self._sandbox.root / "skills", virtual_mode=True
                ),
                "/workspace/": FilesystemBackend(root_dir=workspace, virtual_mode=True),
            },
        )

    def permissions(self) -> list[FilesystemPermission]:
        return [
            FilesystemPermission(
                operations=["read"],
                paths=["/cache/", "/memory/", "/skills/", "/workspace/"],
                mode="allow",
            ),
            FilesystemPermission(
                operations=["write"],
                paths=["/cache/", "/memory/", "/workspace/"],
                mode="allow",
            ),
            FilesystemPermission(
                operations=["write"],
                paths=["/skills/"],
                mode="deny",
            ),
        ]

    def skills(self) -> list[str]:
        return ["/skills/"]

    def memory(self) -> list[str]:
        return ["/memory/AGENTS.md"]

    def disable_subagent_tool(self, model: str) -> None:
        spec = langchain_model_spec(model)
        provider = spec.split(":", 1)[0]
        register_harness_profile(
            provider,
            HarnessProfile(
                general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
            ),
        )

    def build_chat_model(
        self,
        model: str,
        reasoning_effort: str,
        api_key: str | None = None,
    ) -> Any:
        spec = langchain_model_spec(model)
        if not uses_gpt5_reasoning_model(model) and not api_key:
            return spec
        from langchain.chat_models import init_chat_model

        kwargs: dict[str, Any] = {}
        if api_key:
            kwargs["api_key"] = api_key
        if uses_gpt5_reasoning_model(model):
            kwargs["use_responses_api"] = True
            kwargs["reasoning_effort"] = reasoning_effort
        return init_chat_model(spec, **kwargs)
