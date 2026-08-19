from __future__ import annotations

from pathlib import Path
from typing import Any

from route_agent.agent.runtime import AgentRuntime, CompatCache
from route_agent.literature.audit import AuditRef, AuditResult
from route_agent.literature.sandbox import FetchAndParse, LiteratureSandbox
from route_agent.models.agent import AgentCandidate, AgentResult, LLMCall, ToolCall
from route_agent.models.conflict import ConflictTree
from route_agent.models.corpus import FamilyBinding, Provenance
from route_agent.models.request import ModificationFamily
from route_agent.models.verdict import RouteStep
from route_agent.observability import StructuredLogger
from route_agent.post_graph.final_judge import FinalJudgeRunner
from route_agent.verdict.route import reconstruct_route
from tests.support.conflict_fixtures import (
    empty_validation,
    lipid_candidate,
    lipidation_binding,
    make_node,
    make_tree,
    post_graph_report,
    resin_node,
)
from tests.support.fake_tracer import FakeTracer
from tests.support.validation_case import ValidationCase


class RecordingAgent:
    def __init__(self, result: AgentResult) -> None:
        self.payloads: list[dict[str, Any]] = []
        self.result = result

    def invoke(self, payload: dict[str, Any]) -> AgentResult:
        self.payloads.append(payload)
        return self.result


class ScriptedAudit:
    def __init__(self, verified: bool = True) -> None:
        self.verified = verified
        self.calls: list[tuple[str, str, str]] = []

    def verify_citation(self, kind: str, ref_or_source: str, basis: str) -> AuditResult:
        self.calls.append((kind, ref_or_source, basis))
        return AuditResult(
            verified=self.verified,
            reason=None if self.verified else "corpus_ref_not_found",
        )


class TestFinalJudgeRunner(ValidationCase):
    def _tree(self) -> ConflictTree:
        return make_tree(
            [
                resin_node(),
                make_node(
                    "state_1",
                    parents=("state_0",),
                    route_step={
                        "family": "lipidation",
                        "site": "K5",
                        "process": "mtt_lipidation",
                    },
                    candidate=lipid_candidate("mtt_lipidation"),
                    result=AgentResult(objective="check_compatibility", passed=True),
                    modification_ref=0,
                ),
            ],
            [("state_0", "state_1")],
            surviving_ids=("state_1",),
        )

    def _runtime(
        self, tmp_path: Path, result: AgentResult
    ) -> tuple[AgentRuntime, RecordingAgent]:
        sandbox = LiteratureSandbox(tmp_path / "research")
        agent = RecordingAgent(result)
        runtime = AgentRuntime(
            sandbox=sandbox,
            tracer=FakeTracer(),
            logger=StructuredLogger(),
            agent=agent,
            cache=CompatCache(),
        )
        return runtime, agent

    def test_invokes_once_with_winning_trace(self, tmp_path: Path) -> None:
        result = AgentResult(objective="final_judge", confidence="high")
        runtime, agent = self._runtime(tmp_path, result)
        tree = self._tree()
        validation = empty_validation("T-FJ", bindings=(lipidation_binding(),))
        report = post_graph_report("T-FJ", selected_id="state_1")
        route = reconstruct_route(tree, "state_1", object())
        judged = FinalJudgeRunner(runtime, ScriptedAudit(), StructuredLogger()).run(
            self.request(request_id="T-FJ", sequence="ACDEK"),
            validation,
            tree,
            report,
            route,
        )
        assert judged.confidence == "high"
        assert len(agent.payloads) == 1
        payload = agent.payloads[0]
        assert payload["objective"] == "final_judge"
        assert payload["winning_path"] == ["state_0", "state_1"]
        assert payload["route_draft"]
        assert "verdict" not in judged.model_dump()

    def test_payload_includes_all_requested_and_applied_modifications(
        self, tmp_path: Path
    ) -> None:
        result = AgentResult(objective="final_judge", confidence="high")
        runtime, agent = self._runtime(tmp_path, result)
        tree = make_tree(
            [
                resin_node(),
                make_node(
                    "state_1",
                    parents=("state_0",),
                    route_step={
                        "family": "lipidation",
                        "site": "K5",
                        "process": "mtt_lipidation",
                    },
                    candidate=lipid_candidate("mtt_lipidation"),
                    result=AgentResult(objective="check_compatibility", passed=True),
                    modification_ref=0,
                ),
                make_node(
                    "state_2",
                    parents=("state_1",),
                    route_step={
                        "family": "n_term_acetylation",
                        "site": "N-term",
                        "process": "acetic_anhydride",
                    },
                    candidate=AgentCandidate(
                        family="n_term_acetylation",
                        site="N-term",
                        process="acetic_anhydride",
                    ),
                    result=AgentResult(objective="check_compatibility", passed=True),
                    modification_ref=1,
                ),
            ],
            [("state_0", "state_1"), ("state_1", "state_2")],
            surviving_ids=("state_2",),
        )
        acetylation = FamilyBinding(
            modification_ref=1,
            family=ModificationFamily.N_TERM_ACETYLATION,
            sheet="05_N_Term_Acetylation",
            process_ids=("acetic_anhydride",),
            provenance=(
                Provenance(
                    kind="corpus",
                    ref=(
                        "ApexChem_Synthesis_Reactions_by_AminoAcid"
                        ":05_N_Term_Acetylation:4"
                    ),
                ),
            ),
            site="N-term",
        )
        validation = empty_validation(
            "T-FJ-MODS", bindings=(lipidation_binding(), acetylation)
        )
        report = post_graph_report(
            "T-FJ-MODS", selected_id="state_2", surviving_ids=("state_2",)
        )
        judged = FinalJudgeRunner(runtime, ScriptedAudit(), StructuredLogger()).run(
            self.request(
                request_id="T-FJ-MODS",
                sequence="ACDEK",
                modifications=[
                    {"family": "lipidation", "site": "K5", "detail": "C16"},
                    {"family": "n_term_acetylation", "site": "N-term"},
                ],
            ),
            validation,
            tree,
            report,
            reconstruct_route(tree, "state_2", object()),
        )
        assert judged.confidence == "high"
        payload = agent.payloads[0]
        assert payload["requested_modifications"] == [
            {
                "index": 0,
                "family": "lipidation",
                "site": "K5",
                "detail": "C16",
            },
            {
                "index": 1,
                "family": "n_term_acetylation",
                "site": "N-term",
                "detail": None,
            },
        ]
        applied = payload["applied_modifications"]
        assert [item["process"] for item in applied if item.get("process")] == [
            "mtt_lipidation",
            "acetic_anhydride",
        ]
        assert [item["family"] for item in applied if item.get("family")] == [
            "lipidation",
            "n_term_acetylation",
        ]
        assert payload["family_bindings"][0]["family"] == "lipidation"
        assert payload["family_bindings"][1]["family"] == "n_term_acetylation"
        assert payload["site_map"]
        assert payload["resolved_sequence"] == "ACDEK"
        assert payload["candidate"]["process"] == "acetic_anhydride"

    def test_strips_unverified_citations(self, tmp_path: Path) -> None:
        result = AgentResult(
            objective="final_judge",
            confidence="high",
            citations=(
                Provenance(
                    kind="corpus",
                    ref="ApexChem_Synthesis_Reactions_by_AminoAcid:06_Lipidation:25",
                ),
            ),
            llm_call=LLMCall(
                call_id="llm_final_judge",
                model="fake",
                objective="final_judge",
                input_tokens=1,
                output_tokens=1,
                cost_usd=0.0,
                cache={"key": "judge", "hit": False},
                tool_calls=(
                    ToolCall(
                        tool="audit_ref",
                        args={
                            "kind": "corpus",
                            "ref_or_source": (
                                "ApexChem_Synthesis_Reactions_by_AminoAcid"
                                ":06_Lipidation:25"
                            ),
                            "basis": "ivDde",
                        },
                        result_snippet="{}",
                        truncated=False,
                    ),
                ),
            ),
        )
        runtime, _agent = self._runtime(tmp_path, result)
        audit = ScriptedAudit(verified=False)
        judged = FinalJudgeRunner(runtime, audit, StructuredLogger()).run(
            self.request(request_id="T-FJ", sequence="ACDEK"),
            empty_validation("T-FJ", bindings=(lipidation_binding(),)),
            self._tree(),
            post_graph_report("T-FJ", selected_id="state_1"),
            (
                RouteStep(
                    step=1,
                    stage="resin_selection",
                    operation="Select Wang",
                    provenance=(Provenance(kind="inference", basis="resin"),),
                ),
            ),
        )
        assert judged.citations == ()
        assert any("unverified_citation" in item for item in judged.unknowns)
        assert judged.confidence == "medium"
        assert audit.calls[0][2] == "ivDde"

    def test_keeps_inference_without_audit(self, tmp_path: Path) -> None:
        result = AgentResult(
            objective="final_judge",
            confidence="medium",
            citations=(Provenance(kind="inference", basis="mechanism"),),
        )
        runtime, _agent = self._runtime(tmp_path, result)
        audit = ScriptedAudit(verified=False)
        judged = FinalJudgeRunner(runtime, audit, StructuredLogger()).run(
            self.request(request_id="T-FJ", sequence="ACDEK"),
            empty_validation("T-FJ"),
            self._tree(),
            post_graph_report("T-FJ", selected_id="state_1"),
            (),
        )
        assert judged.citations[0].kind == "inference"
        assert audit.calls == []

    def test_thin_cache_cannot_support_external(self, tmp_path: Path) -> None:
        sandbox = LiteratureSandbox(tmp_path / "research")
        FetchAndParse(sandbox=sandbox).cache_document(
            "https://pubs.acs.org/thin",
            "short",
        )
        result = AgentResult(
            objective="final_judge",
            confidence="medium",
            citations=(
                Provenance(
                    kind="external",
                    source="https://pubs.acs.org/thin",
                    basis="short",
                ),
            ),
        )
        agent = RecordingAgent(result)
        runtime = AgentRuntime(
            sandbox=sandbox,
            tracer=FakeTracer(),
            logger=StructuredLogger(),
            agent=agent,
            cache=CompatCache(),
        )
        judged = FinalJudgeRunner(
            runtime,
            AuditRef(sandbox=sandbox, families_path=self.families_path),
            StructuredLogger(),
        ).run(
            self.request(request_id="T-FJ", sequence="ACDEK"),
            empty_validation("T-FJ"),
            self._tree(),
            post_graph_report("T-FJ", selected_id="state_1"),
            (),
        )
        assert judged.citations == ()
        assert any("thin_content" in item for item in judged.unknowns)

    def test_no_winner_skips_model(self, tmp_path: Path) -> None:
        runtime, agent = self._runtime(
            tmp_path, AgentResult(objective="final_judge", confidence="high")
        )
        judged = FinalJudgeRunner(runtime, ScriptedAudit(), StructuredLogger()).run(
            self.request(request_id="T-FJ", sequence="ACDEK"),
            empty_validation("T-FJ", status="fail"),
            make_tree([resin_node()], []),
            post_graph_report("T-FJ", selected_id=None),
            (),
        )
        assert agent.payloads == []
        assert judged.confidence == "low"
        assert "no winning candidate" in judged.unknowns
        assert "verdict" not in judged.model_dump()
