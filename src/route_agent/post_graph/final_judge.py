from __future__ import annotations

from typing import Any, Protocol

from route_agent.agent.runtime import AgentRuntime
from route_agent.literature.audit import AuditResult
from route_agent.literature.sandbox import THIN_CONTENT_CHARS
from route_agent.models.agent import AgentCandidate, AgentConfidence, AgentResult
from route_agent.models.conflict import ConflictTree, ValidationResult
from route_agent.models.corpus import Provenance
from route_agent.models.molecular import PostGraphValidationReport
from route_agent.models.request import DesignRequest
from route_agent.models.verdict import RouteStep
from route_agent.observability import StructuredLogger
from route_agent.verdict.path import collect_winning_path, path_nodes

CONFIDENCE_RANK = {"high": 0, "medium": 1, "low": 2}


class CitationAuditor(Protocol):
    def verify_citation(
        self, kind: str, ref_or_source: str, basis: str
    ) -> AuditResult: ...


class FinalJudgeRunner:
    def __init__(
        self,
        runtime: AgentRuntime,
        audit: CitationAuditor,
        logger: StructuredLogger | None = None,
    ) -> None:
        self._runtime = runtime
        self._audit = audit
        self._logger = logger or StructuredLogger("route_agent.final_judge")

    def run(
        self,
        request: DesignRequest,
        validation: ValidationResult,
        tree: ConflictTree,
        post_graph: PostGraphValidationReport,
        route_draft: tuple[RouteStep, ...],
    ) -> AgentResult:
        if post_graph.selected_id is None:
            self._logger.info(
                "final_judge_skipped",
                request_id=request.request_id,
                reason="no winning candidate",
            )
            return AgentResult(
                objective="final_judge",
                confidence="low",
                unknowns=("no winning candidate",),
            )
        winner = tree.node(post_graph.selected_id)
        candidate = winner.candidate or AgentCandidate(
            family="unknown", site="unknown", process="unknown"
        )
        context = self._build_context(
            request,
            validation,
            tree,
            post_graph,
            route_draft,
            winner.state.output,
        )
        self._logger.info(
            "final_judge_start",
            request_id=request.request_id,
            selected_id=post_graph.selected_id,
            process=candidate.process,
        )
        result = self._runtime.invoke(
            "final_judge",
            request,
            winner.state.output,
            candidate,
            context=context,
        )
        gated = self._gate_citations(result)
        judged = gated.model_copy(
            update={
                "objective": "final_judge",
                "confidence": self._floor_confidence(
                    gated, validation, tree, post_graph
                ),
            }
        )
        self._logger.info(
            "final_judge_done",
            request_id=request.request_id,
            passed=judged.passed,
            confidence=judged.confidence,
            citations=len(judged.citations),
            unknowns=len(judged.unknowns),
        )
        return judged

    def _build_context(
        self,
        request: DesignRequest,
        validation: ValidationResult,
        tree: ConflictTree,
        post_graph: PostGraphValidationReport,
        route_draft: tuple[RouteStep, ...],
        output: dict[str, Any],
    ) -> dict[str, Any]:
        winner = next(
            (
                item
                for item in post_graph.candidates
                if item.node_id == post_graph.selected_id
            ),
            None,
        )
        return {
            "requested_modifications": [
                {
                    "index": index,
                    "family": item.family.value,
                    "site": item.site,
                    "detail": item.detail,
                }
                for index, item in enumerate(request.modifications)
            ],
            "applied_modifications": self._applied_modifications(
                tree, post_graph.selected_id
            ),
            "family_bindings": [
                item.model_dump(mode="json") for item in validation.family_bindings
            ],
            "site_map": [item.model_dump(mode="json") for item in validation.site_map],
            "resolved_sequence": validation.resolved_sequence,
            "resolved_annotations": dict(validation.resolved_annotations),
            "winning_path": list(collect_winning_path(tree, post_graph.selected_id)),
            "path_status": [
                node.state.status for node in path_nodes(tree, post_graph.selected_id)
            ],
            "unmapped_spans": [
                span.model_dump(mode="json")
                for span in validation.occupancy.unmapped_spans
            ],
            "route_draft": [step.model_dump(mode="json") for step in route_draft],
            "catalysts_used": output.get("catalysts_used") or {},
            "molecular": None
            if winner is None
            else winner.molecular.model_dump(mode="json"),
            "intent_result": None
            if winner is None or winner.intent is None
            else winner.intent.model_dump(mode="json"),
            "unknowns": list(validation.unknowns) + list(post_graph.unknowns),
        }

    def _applied_modifications(
        self, tree: ConflictTree, selected_id: str | None
    ) -> list[dict[str, Any]]:
        applied: list[dict[str, Any]] = []
        for node in path_nodes(tree, selected_id):
            step = node.state.route_step or {}
            candidate = node.candidate
            if candidate is None and not step:
                continue
            result = node.agent_result
            item: dict[str, Any] = {
                "node_id": node.state.id,
                "modification_ref": node.state.modification_ref,
                "status": node.state.status,
                "passed": None if result is None else result.passed,
            }
            if step.get("stage") == "resin_selection":
                item.update(
                    {
                        "stage": "resin_selection",
                        "operation": step.get("operation"),
                        "resin": step.get("resin"),
                    }
                )
            else:
                item.update(
                    {
                        "family": (
                            candidate.family
                            if candidate is not None
                            else step.get("family")
                        ),
                        "site": (
                            candidate.site
                            if candidate is not None
                            else step.get("site")
                        ),
                        "process": (
                            candidate.process
                            if candidate is not None
                            else step.get("process")
                        ),
                        "findings": []
                        if result is None
                        else [
                            finding.model_dump(mode="json")
                            for finding in result.findings
                        ],
                    }
                )
            applied.append(item)
        return applied

    def _gate_citations(self, result: AgentResult) -> AgentResult:
        kept: list[Provenance] = []
        unknowns = list(result.unknowns)
        stripped = False
        for citation in result.citations:
            if citation.kind == "inference":
                kept.append(citation)
                continue
            basis = citation.basis or self._basis_from_tools(result, citation)
            target = citation.ref or citation.source or ""
            audit = self._audit.verify_citation(citation.kind, target, basis)
            if not audit.verified:
                stripped = True
                unknowns.append(f"unverified_citation:{target}")
                continue
            if citation.kind == "external" and self._is_thin(target):
                stripped = True
                unknowns.append(f"thin_content:{target}")
                continue
            kept.append(citation)
        return result.model_copy(
            update={
                "citations": tuple(kept),
                "unknowns": tuple(dict.fromkeys(unknowns)),
                "confidence": self._at_least(
                    result.confidence, "medium" if stripped else result.confidence
                ),
            }
        )

    def _basis_from_tools(self, result: AgentResult, citation: Provenance) -> str:
        target = citation.ref or citation.source
        call = result.llm_call
        if call is None:
            return ""
        for tool in call.tool_calls:
            if tool.tool != "audit_ref":
                continue
            if tool.args.get("ref_or_source") == target:
                return str(tool.args.get("basis") or "")
        return ""

    def _is_thin(self, source: str) -> bool:
        sandbox = getattr(self._audit, "_sandbox", None)
        if sandbox is None:
            return False
        path = sandbox.cached_markdown_path(source)
        if path is None:
            return False
        return len(path.read_text(encoding="utf-8")) < THIN_CONTENT_CHARS

    def _floor_confidence(
        self,
        result: AgentResult,
        validation: ValidationResult,
        tree: ConflictTree,
        post_graph: PostGraphValidationReport,
    ) -> AgentConfidence:
        confidence = result.confidence or "low"
        if result.passed is None and "model disabled" in result.unknowns:
            return "low"
        if validation.occupancy.unmapped_spans:
            confidence = self._at_least(confidence, "medium")
        if any(
            node.state.status == "degraded"
            for node in path_nodes(tree, post_graph.selected_id)
        ):
            confidence = self._at_least(confidence, "medium")
        if any(item.startswith("unverified_citation:") for item in result.unknowns):
            confidence = self._at_least(confidence, "medium")
        if any(item.startswith("thin_content:") for item in result.unknowns):
            confidence = self._at_least(confidence, "medium")
        return confidence

    def _at_least(
        self, current: AgentConfidence | None, floor: AgentConfidence | None
    ) -> AgentConfidence:
        if floor is None:
            return current or "low"
        if current is None:
            return floor
        if CONFIDENCE_RANK[current] >= CONFIDENCE_RANK[floor]:
            return current
        return floor
