from __future__ import annotations

from pathlib import Path
from typing import Any

from route_agent.agent.runtime import AgentRuntime, CompatCache
from route_agent.conflict import ConflictWalker
from route_agent.corpus import CorpusRepository
from route_agent.literature.sandbox import LiteratureSandbox
from route_agent.models.agent import AgentResult, LLMCall
from route_agent.models.conflict import State, ValidationResult
from route_agent.models.corpus import FamilyBinding
from route_agent.models.request import ModificationFamily, ResolvedSite, SiteMapEntry
from route_agent.models.validation import StructuredFreeText
from route_agent.molecular.analysis import MolecularAnalyzer, MolecularConfig
from route_agent.observability import StructuredLogger
from route_agent.post_graph.validator import PostGraphValidator
from tests.support.fake_tracer import FakeTracer
from tests.support.validation_case import ValidationCase


class RecordingAgent:
    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    def invoke(self, payload: dict[str, Any]) -> AgentResult:
        self.payloads.append(payload)
        intent_fail = payload.get("objective") == "check_intent" and payload.get(
            "force_intent_fail"
        )
        return AgentResult(
            objective=payload["objective"],
            passed=not intent_fail,
            llm_call=LLMCall(
                call_id="llm_test",
                model="fake",
                objective=payload["objective"],
                input_tokens=1,
                output_tokens=1,
                cost_usd=0.0,
                cache={"key": "fake", "hit": False},
            ),
        )


class TestPostGraphValidator(ValidationCase):
    def _state(self) -> State:
        return State(
            id="state_0",
            node_type="validation",
            parents=(),
            modification_ref=None,
            status="pass",
            output={
                "protected": {},
                "resolved_sequence": "ACDEK",
                "residue_annotations": {},
                "parent_c_terminus": "amide",
            },
            building_block=None,
            sequence_snapshot="ACDEK",
            route_step={"stage": "resin_selection", "resin": "Rink"},
            errors=(),
            provenance=(),
            llm_calls=(),
        )

    def _validation(
        self, request: Any, bindings: tuple[FamilyBinding, ...]
    ) -> ValidationResult:
        sites = tuple(
            ResolvedSite(
                modification_ref=index,
                requested_token=modification.site,
                atoms=(),
            )
            for index, modification in enumerate(request.modifications)
        )
        site_map = tuple(
            SiteMapEntry(
                requested=modification.site,
                resolved=modification.site,
                residue=modification.site[:1],
                note=None,
            )
            for modification in request.modifications
        )
        return ValidationResult(
            request_id=request.request_id,
            state=self._state(),
            residues=(),
            sites_resolved=sites,
            parent_c_terminus=request.parent_c_terminus,
            parent_features=request.parent_features,
            residue_annotations=dict(request.residue_annotations),
            occupancy=StructuredFreeText(features=(), occupancy=(), route_seed=()),
            intent=request.intent,
            family_bindings=bindings,
            resolved_sequence=request.sequence,
            resolved_annotations=dict(request.residue_annotations),
            index_map=(),
            site_map=site_map,
            conflicts=(),
            unknowns=(),
        )

    def test_validates_survivors_and_calls_intent(self, tmp_path: Path) -> None:
        request = self.request(
            request_id="T-PG",
            sequence="ACDEK",
            parent_c_terminus="amide",
            modifications=[{"family": "n_term_acetylation", "site": "N-term"}],
        )
        bindings = (
            FamilyBinding(
                modification_ref=0,
                family=ModificationFamily.N_TERM_ACETYLATION,
                sheet="sheet",
                process_ids=("n_term_acetylation_default",),
                provenance=(),
            ),
        )
        sandbox = LiteratureSandbox(tmp_path / "research")
        agent = RecordingAgent()
        runtime = AgentRuntime(
            sandbox=sandbox,
            tracer=FakeTracer(),
            logger=StructuredLogger(),
            agent=agent,
            cache=CompatCache(),
        )
        walker = ConflictWalker(
            runtime, CorpusRepository(self.families_path), check_timeout_s=0
        )
        tree = walker.walk(request, self._validation(request, bindings))
        report = PostGraphValidator(
            runtime,
            MolecularAnalyzer(config=MolecularConfig(skip_3d=True)),
        ).validate(request, self._validation(request, bindings), tree)

        assert tree.surviving_ids
        assert report.selected_id in tree.surviving_ids
        assert "verdict" not in report.model_dump()
        intent_payloads = [
            payload
            for payload in agent.payloads
            if payload["objective"] == "check_intent"
        ]
        assert intent_payloads
        assert intent_payloads[0]["molecular_validation"]["valid"] is True
        assert intent_payloads[0]["molecular_validation"]["formula"]
        winner = next(
            item for item in report.candidates if item.node_id == report.selected_id
        )
        assert winner.molecular.two_d.valid is True
        assert winner.intent is not None
        assert winner.intent.objective == "check_intent"
