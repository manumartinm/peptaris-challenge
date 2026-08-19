from __future__ import annotations

from typing import Any, Protocol

from route_agent.models.agent import AgentResult, ProcessProfile
from route_agent.models.corpus import FamilyBinding, TargetLookupResult
from route_agent.models.request import DesignRequest
from route_agent.models.validation import StructuringResult, ValidationError


class Run(Protocol):
    def span(self, name: str, metadata: dict[str, Any], **kwargs: Any) -> Any: ...

    def generation(self, name: str, metadata: dict[str, Any], **kwargs: Any) -> Any: ...

    def trace_context(self) -> dict[str, str] | None: ...


class Tracer(Protocol):
    def start_run(self, request_id: str, metadata: dict[str, Any]) -> Any: ...

    def current_run(self) -> Run | None: ...

    def flush(self) -> None: ...


class Structurer(Protocol):
    def structure_request(self, request: DesignRequest) -> StructuringResult: ...


class DeepAgent(Protocol):
    def invoke(self, payload: dict[str, Any]) -> AgentResult: ...


class FamilyLookup(Protocol):
    """Corpus lookup used by the walker, parser, and route reconstructor."""

    def bind_families(
        self, request: DesignRequest
    ) -> tuple[tuple[FamilyBinding, ...], tuple[ValidationError, ...]]: ...

    def lookup_family_process(self, family: str, process_id: str) -> ProcessProfile: ...

    def lookup_target(self, peptide: str) -> TargetLookupResult: ...
