from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path
from typing import Any

from route_agent.agent.runtime import AgentRuntime, CompatCache
from route_agent.conflict import ConflictWalker, _resolve_pending_handles
from route_agent.corpus import CorpusRepository
from route_agent.literature.sandbox import LiteratureSandbox
from route_agent.models.agent import AgentCandidate, AgentFinding, AgentResult, LLMCall
from route_agent.models.conflict import State, ValidationResult
from route_agent.models.corpus import FamilyBinding
from route_agent.models.request import (
    ModificationFamily,
    ResolvedSite,
    SiteAtom,
    SiteMapEntry,
)
from route_agent.models.validation import StructuredFreeText
from route_agent.observability import StructuredLogger
from route_agent.observe import RecordingObserver
from route_agent.parser.sequence import SequenceValidator
from route_agent.parser.sites import SiteValidator
from route_agent.verdict.assembler import RouteAssembler
from tests.support.agents import ScriptedAgent, SleepingOnProcessAgent
from tests.support.conflict_fixtures import post_graph_report
from tests.support.fake_tracer import FakeTracer
from tests.support.validation_case import (
    GLUCAGON,
    OCTREOTIDE,
    TERIPARATIDE,
    ValidationCase,
)


class TestConflictWalker(ValidationCase):
    def _state(self, *, status: str = "pass") -> State:
        return State(
            id="state_0",
            node_type="validation",
            parents=(),
            modification_ref=None,
            status=status,  # type: ignore[arg-type]
            output={
                "protected": {"K12": "pending"},
                "occupancy": [],
                "route_seed": [],
                "parent_c_terminus": "free_acid",
                "parent_features": [],
                "residue_annotations": {},
                "intent": "unit test",
                "resolved_sequence": GLUCAGON,
                "site_map": [],
            },
            building_block=None,
            sequence_snapshot=GLUCAGON,
            route_step={"stage": "resin_selection", "resin": "Wang"},
            errors=(),
            provenance=(),
            llm_calls=(),
        )

    def _binding(
        self,
        *,
        modification_ref: int,
        family: ModificationFamily,
        process_ids: tuple[str, ...],
        sheet: str = "sheet",
    ) -> FamilyBinding:
        return FamilyBinding(
            modification_ref=modification_ref,
            family=family,
            sheet=sheet,
            process_ids=process_ids,
            provenance=(),
        )

    def _validation(
        self,
        request: Any,
        bindings: tuple[FamilyBinding, ...],
        *,
        status: str = "pass",
    ) -> ValidationResult:
        sequence = SequenceValidator().validate_parent_sequence(
            request.sequence, request.residue_annotations
        )
        parsed = SiteValidator().validate_modification_sites(request, sequence.residues)
        return ValidationResult(
            request_id=request.request_id,
            state=self._state(status=status),
            residues=sequence.residues,
            sites_resolved=parsed.sites_resolved,
            parent_c_terminus=request.parent_c_terminus,
            parent_features=request.parent_features,
            residue_annotations=dict(request.residue_annotations),
            occupancy=StructuredFreeText(features=(), occupancy=(), route_seed=()),
            intent=request.intent,
            family_bindings=bindings,
            resolved_sequence=request.sequence,
            resolved_annotations=dict(request.residue_annotations),
            index_map=(),
            site_map=parsed.site_map,
            conflicts=(),
            unknowns=(),
        )

    def _walker(
        self,
        tmp_path: Path,
        outcomes: dict[str, bool | None] | None = None,
        observer: RecordingObserver | None = None,
    ) -> tuple[ConflictWalker, ScriptedAgent, CompatCache]:
        sandbox = LiteratureSandbox(tmp_path / "research")
        agent = ScriptedAgent(outcomes)
        cache = CompatCache()
        runtime = AgentRuntime(
            sandbox=sandbox,
            tracer=FakeTracer(),
            logger=StructuredLogger(),
            agent=agent,
            cache=cache,
        )
        walker = ConflictWalker(
            runtime,
            CorpusRepository(self.families_path),
            check_timeout_s=0,
            observer=observer or RecordingObserver(),
        )
        return walker, agent, cache

    def test_staple_bridge_stays_one_site_not_two_modifications(
        self, tmp_path: Path
    ) -> None:
        request = self.request(
            request_id="REQ-03",
            parent_name="teriparatide",
            sequence=TERIPARATIDE,
            modifications=[
                {
                    "family": "hydrocarbon_stapling",
                    "site": "V21,R25",
                    "detail": "i,i+4 all-hydrocarbon staple",
                }
            ],
        )
        bindings = (
            self._binding(
                modification_ref=0,
                family=ModificationFamily.HYDROCARBON_STAPLING,
                process_ids=("hydrocarbon_stapling_default",),
            ),
        )
        validation = self._validation(request, bindings)
        validation = validation.model_copy(
            update={
                "sites_resolved": (
                    ResolvedSite(
                        modification_ref=0,
                        requested_token="V21,R25",
                        atoms=(
                            SiteAtom(
                                kind="position", letter="V", index=21, token="V21"
                            ),
                            SiteAtom(
                                kind="position", letter="R", index=25, token="R25"
                            ),
                        ),
                    ),
                ),
                "site_map": (
                    SiteMapEntry(
                        requested="V21,R25",
                        resolved="V21",
                        residue="Val",
                        note=None,
                    ),
                    SiteMapEntry(
                        requested="V21,R25",
                        resolved="R25",
                        residue="Arg",
                        note=None,
                    ),
                ),
            }
        )
        walker, agent, _cache = self._walker(tmp_path)

        tree = walker.walk(request, validation)

        child = tree.node("state_1")
        assert child.candidate is not None
        assert child.candidate.site == "V21,R25"
        assert tree.surviving_ids == ("state_1",)
        assert [payload["candidate"]["site"] for payload in agent.payloads] == [
            "V21,R25"
        ]
        output = child.state.output
        assert output["residue_overrides"] == {"V21": "s5", "R25": "s5"}
        assert output["permanent_connectivity"][0]["bond_type"] == "olefin"
        assert "unparsed_staple_site" not in str(output.get("product_unknowns") or [])

    def test_multi_disulfide_is_one_stage_with_all_bridges(
        self, tmp_path: Path
    ) -> None:
        request = self.request(
            request_id="REQ-10",
            parent_name="linaclotide",
            sequence="CCEYCCNPACTGCY",
            modifications=[
                {
                    "family": "disulfide",
                    "site": "C1-C6, C2-C10, C5-C13",
                    "detail": "regioselective three-bridge folding",
                }
            ],
        )
        bindings, errors = CorpusRepository(self.families_path).bind_families(request)
        assert errors == ()
        assert len(bindings) == 1
        walker, agent, _cache = self._walker(tmp_path)

        tree = walker.walk(request, self._validation(request, bindings))

        children = [tree.node(node_id) for node_id in tree.graph.successors("state_0")]
        assert children
        assert [node.candidate.site for node in children if node.candidate] == [
            "C1-C6, C2-C10, C5-C13"
        ] * len(children)
        for child in children:
            pairs = {
                (bond["from_atom"], bond["to_fragment"])
                for bond in child.state.output.get("permanent_connectivity") or []
                if bond["bond_type"] == "disulfide"
            }
            assert pairs == {
                ("C1.SG", "C6.SG"),
                ("C2.SG", "C10.SG"),
                ("C5.SG", "C13.SG"),
            }
            assert list(tree.graph.successors(child.state.id)) == []
        assert [payload["candidate"]["site"] for payload in agent.payloads] == [
            "C1-C6, C2-C10, C5-C13"
        ] * len(children)

    def test_pending_handles_cover_every_cysteine_in_the_bridge_set(self) -> None:
        updated = _resolve_pending_handles(
            {"protected": {"C1": "pending", "C6": "pending", "K12": "pending"}},
            AgentCandidate(
                family="disulfide",
                site="C1-C6, C2-C10, C5-C13",
                process="acm_oxidation",
            ),
        )
        assert updated["protected"]["C1"] == "Acm"
        assert updated["protected"]["C6"] == "Acm"
        assert updated["protected"]["K12"] == "pending"

    def test_single_process_child_sees_state_zero_ledgers(self, tmp_path: Path) -> None:
        request = self.request(
            request_id="T-ONE",
            sequence=GLUCAGON,
            modifications=[{"family": "n_term_acetylation", "site": "N-term"}],
        )
        original = tuple(request.modifications)
        bindings = (
            self._binding(
                modification_ref=0,
                family=ModificationFamily.N_TERM_ACETYLATION,
                process_ids=("n_term_acetylation_default",),
            ),
        )
        walker, agent, _cache = self._walker(tmp_path)

        tree = walker.walk(request, self._validation(request, bindings))

        assert request.modifications == original
        assert list(tree.graph.successors("state_0")) == ["state_1"]
        child = tree.node("state_1")
        assert child.candidate is not None
        assert child.candidate.process == "n_term_acetylation_default"
        assert child.state.modification_ref == 0
        assert child.state.route_step is not None
        assert tree.surviving_ids == ("state_1",)
        payload = agent.payloads[0]["state"]
        assert payload["protected"]["K12"] == "Boc"
        assert payload["history"] == []
        assert payload["sequence_snapshot"] == GLUCAGON
        assert payload["route_step"]["resin"] == "Wang"
        assert payload["resin"] == "Wang"
        profile = agent.payloads[0]["process_profile"]
        assert profile["found"] is True
        assert profile["process_id"] == "n_term_acetylation_default"
        assert "conditions" in profile
        prior = agent.payloads[0]["prior"]
        assert prior["resin"] == "Wang"
        assert prior["parent_c_terminus"] == "free_acid"
        assert agent.payloads[0]["state"]["termini"]["n"] == "Fmoc"
        assert child.state.output["permanent_connectivity"][0]["to_fragment"] == (
            "acetyl:1"
        )
        assert child.state.output["termini"]["n"] == "acetyl"

    def test_lipidation_opens_three_siblings_from_root(self, tmp_path: Path) -> None:
        request = self.request(
            request_id="T-LIP",
            sequence=GLUCAGON,
            modifications=[{"family": "lipidation", "site": "K12"}],
        )
        bindings = (
            self._binding(
                modification_ref=0,
                family=ModificationFamily.LIPIDATION,
                process_ids=(
                    "mtt_lipidation",
                    "ivdde_lipidation",
                    "alloc_lipidation",
                ),
                sheet="06_Lipidation",
            ),
        )
        walker, agent, _cache = self._walker(tmp_path)

        tree = walker.walk(request, self._validation(request, bindings))
        children = [tree.node(node_id) for node_id in tree.graph.successors("state_0")]

        assert [node.candidate.process for node in children if node.candidate] == [
            "mtt_lipidation",
            "ivdde_lipidation",
            "alloc_lipidation",
        ]
        assert len(agent.payloads) == 3
        assert all(node.state.parents == ("state_0",) for node in children)

    def test_two_by_two_fanout_from_each_passing_parent(self, tmp_path: Path) -> None:
        request = self.request(
            request_id="T-2X2",
            sequence=GLUCAGON,
            modifications=[
                {"family": "special_residues", "site": "M27", "detail": "Met->Nle"},
                {"family": "lipidation", "site": "K12"},
            ],
        )
        bindings = (
            self._binding(
                modification_ref=0,
                family=ModificationFamily.SPECIAL_RESIDUES,
                process_ids=("p1a", "p1b"),
            ),
            self._binding(
                modification_ref=1,
                family=ModificationFamily.LIPIDATION,
                process_ids=("p2x", "p2y"),
            ),
        )
        walker, agent, _cache = self._walker(tmp_path)

        tree = walker.walk(request, self._validation(request, bindings))
        first = list(tree.graph.successors("state_0"))
        leaves = [child for parent in first for child in tree.graph.successors(parent)]

        assert len(first) == 2
        assert len(leaves) == 4
        assert tree.surviving_ids == tuple(leaves)
        for parent in first:
            processes = []
            for child in tree.graph.successors(parent):
                candidate = tree.node(child).candidate
                if candidate is not None:
                    processes.append(candidate.process)
            assert processes == ["p2x", "p2y"]
            history = tree.node(parent).state.output["history"]
            assert len(history) == 1
            for child in tree.graph.successors(parent):
                child_history = tree.node(child).state.output["history"]
                assert child_history[0] == history[0]
                assert child_history[1]["process"] in {"p2x", "p2y"}
        second_layer = [
            payload
            for payload in agent.payloads
            if payload["candidate"]["process"] in {"p2x", "p2y"}
        ]
        assert second_layer
        assert second_layer[0]["state"]["history"][0]["process"] in {"p1a", "p1b"}

    def test_failed_sibling_has_no_children_passing_sibling_fans_out(
        self, tmp_path: Path
    ) -> None:
        request = self.request(
            request_id="T-PRUNE",
            sequence=GLUCAGON,
            modifications=[
                {"family": "special_residues", "site": "M27", "detail": "Met->Nle"},
                {"family": "lipidation", "site": "K12"},
            ],
        )
        bindings = (
            self._binding(
                modification_ref=0,
                family=ModificationFamily.SPECIAL_RESIDUES,
                process_ids=("p1a", "p1b"),
            ),
            self._binding(
                modification_ref=1,
                family=ModificationFamily.LIPIDATION,
                process_ids=("p2x", "p2y"),
            ),
        )
        walker, _agent, _cache = self._walker(tmp_path, outcomes={"p1a": False})

        tree = walker.walk(request, self._validation(request, bindings))
        first = [tree.node(node_id) for node_id in tree.graph.successors("state_0")]
        failed = next(
            node for node in first if node.candidate and node.candidate.process == "p1a"
        )
        passed = next(
            node for node in first if node.candidate and node.candidate.process == "p1b"
        )

        assert failed.state.route_step is None
        assert list(tree.graph.successors(failed.state.id)) == []
        child_processes = []
        for child in tree.graph.successors(passed.state.id):
            candidate = tree.node(child).candidate
            if candidate is not None:
                child_processes.append(candidate.process)
        assert child_processes == ["p2x", "p2y"]
        assert len(tree.surviving_ids) == 2

    def test_three_modifications_stop_at_depth_three(self, tmp_path: Path) -> None:
        request = self.request(
            request_id="T-DEPTH",
            sequence=GLUCAGON,
            modifications=[
                {"family": "special_residues", "site": "M27", "detail": "Met->Nle"},
                {"family": "n_term_acetylation", "site": "N-term"},
                {"family": "lipidation", "site": "K12"},
            ],
        )
        bindings = (
            self._binding(
                modification_ref=0,
                family=ModificationFamily.SPECIAL_RESIDUES,
                process_ids=("p1",),
            ),
            self._binding(
                modification_ref=1,
                family=ModificationFamily.N_TERM_ACETYLATION,
                process_ids=("p2",),
            ),
            self._binding(
                modification_ref=2,
                family=ModificationFamily.LIPIDATION,
                process_ids=("p3",),
            ),
        )
        walker, _agent, _cache = self._walker(tmp_path)

        tree = walker.walk(request, self._validation(request, bindings))
        depths = [
            len(tree.node(node_id).state.output.get("history") or [])
            for node_id in tree.graph.nodes
        ]

        assert max(depths) == 3
        assert tree.surviving_ids == ("state_3",)
        assert tree.node("state_3").state.output["applied"]["process"] == "p3"

    def test_failed_root_is_not_expanded(self, tmp_path: Path) -> None:
        request = self.request(
            request_id="T-FAIL",
            sequence=GLUCAGON,
            modifications=[{"family": "lipidation", "site": "K12"}],
        )
        bindings = (
            self._binding(
                modification_ref=0,
                family=ModificationFamily.LIPIDATION,
                process_ids=("mtt_lipidation",),
            ),
        )
        walker, agent, _cache = self._walker(tmp_path)

        tree = walker.walk(request, self._validation(request, bindings, status="fail"))

        assert list(tree.graph.nodes) == ["state_0"]
        assert tree.surviving_ids == ()
        assert agent.payloads == []

    def test_degraded_node_stays_on_frontier(self, tmp_path: Path) -> None:
        request = self.request(
            request_id="T-DEG",
            sequence=GLUCAGON,
            modifications=[
                {"family": "special_residues", "site": "M27", "detail": "Met->Nle"},
                {"family": "lipidation", "site": "K12"},
            ],
        )
        bindings = (
            self._binding(
                modification_ref=0,
                family=ModificationFamily.SPECIAL_RESIDUES,
                process_ids=("p1a",),
            ),
            self._binding(
                modification_ref=1,
                family=ModificationFamily.LIPIDATION,
                process_ids=("p2x",),
            ),
        )
        walker, _agent, _cache = self._walker(tmp_path, outcomes={"p1a": None})

        tree = walker.walk(request, self._validation(request, bindings))
        first = tree.node("state_1")

        assert first.state.status == "degraded"
        assert first.state.route_step == {
            "family": "special_residues",
            "site": "M27",
            "process": "p1a",
        }
        assert list(tree.graph.successors("state_1")) == ["state_2"]

    def test_agent_error_does_not_pass_or_survive(self, tmp_path: Path) -> None:
        request = self.request(
            request_id="T-ERR",
            sequence=GLUCAGON,
            modifications=[{"family": "n_term_acetylation", "site": "N-term"}],
        )
        bindings = (
            self._binding(
                modification_ref=0,
                family=ModificationFamily.N_TERM_ACETYLATION,
                process_ids=("n_term_acetylation_default",),
            ),
        )

        class BoomAgent(ScriptedAgent):
            def invoke(self, payload: dict[str, Any]) -> AgentResult:
                return AgentResult(
                    objective=payload["objective"],
                    passed=None,
                    unknowns=("agent_invoke_failed:ValueError",),
                )

        sandbox = LiteratureSandbox(tmp_path / "research")
        runtime = AgentRuntime(
            sandbox=sandbox,
            tracer=FakeTracer(),
            logger=StructuredLogger(),
            agent=BoomAgent(),
            cache=CompatCache(),
        )
        walker = ConflictWalker(
            runtime, CorpusRepository(self.families_path), check_timeout_s=0
        )

        tree = walker.walk(request, self._validation(request, bindings))
        child = tree.node("state_1")

        assert child.state.status == "degraded"
        assert child.state.route_step is None
        assert tree.surviving_ids == ()

    def test_cache_misses_when_history_differs(self, tmp_path: Path) -> None:
        request = self.request(
            request_id="T-CACHE",
            sequence=GLUCAGON,
            modifications=[
                {"family": "special_residues", "site": "M27", "detail": "Met->Nle"},
                {"family": "lipidation", "site": "K12"},
            ],
        )
        bindings = (
            self._binding(
                modification_ref=0,
                family=ModificationFamily.SPECIAL_RESIDUES,
                process_ids=("p1a", "p1b"),
            ),
            self._binding(
                modification_ref=1,
                family=ModificationFamily.LIPIDATION,
                process_ids=("p2x", "p2y"),
            ),
        )
        walker, agent, cache = self._walker(tmp_path)

        tree = walker.walk(request, self._validation(request, bindings))
        processes = [payload["candidate"]["process"] for payload in agent.payloads]
        second_hits = [
            tree.node(node_id).agent_result for node_id in tree.surviving_ids
        ]

        assert Counter(processes) == Counter(["p1a", "p1b", "p2x", "p2y", "p2x", "p2y"])
        assert cache.state_categories_present(
            {
                "protected": {"K12": "pending"},
                "history": [{"process": "p1a"}],
            }
        ) != cache.state_categories_present(
            {
                "protected": {"K12": "pending"},
                "history": [{"process": "p1b"}],
            }
        )
        assert all(
            result is None
            or result.llm_call is None
            or result.llm_call.cache.get("hit") is not True
            for result in second_hits
        )

    def test_cache_hit_does_not_reuse_findings_from_another_site(
        self, tmp_path: Path
    ) -> None:
        request = self.request(
            request_id="T-SITE-FINDINGS",
            sequence="ACDEKK",
            modifications=[
                {"family": "lipidation", "site": "K5"},
                {"family": "pegylation", "site": "K6"},
            ],
        )
        bindings = (
            self._binding(
                modification_ref=0,
                family=ModificationFamily.LIPIDATION,
                process_ids=("alloc_lipidation",),
            ),
            self._binding(
                modification_ref=1,
                family=ModificationFamily.PEGYLATION,
                process_ids=("alloc_lipidation",),
            ),
        )
        sandbox = LiteratureSandbox(tmp_path / "research")

        class SiteTaggedAgent:
            def __init__(self) -> None:
                self.payloads: list[dict[str, Any]] = []

            def invoke(self, payload: dict[str, Any]) -> AgentResult:
                self.payloads.append(payload)
                site = str(payload["candidate"]["site"])
                return AgentResult(
                    objective="check_compatibility",
                    passed=True,
                    findings=(
                        AgentFinding(
                            kind="protecting_group_orthogonality",
                            description=f"checked {site}",
                            affected=(site,),
                        ),
                    ),
                    llm_call=LLMCall(
                        call_id="llm_check_compatibility",
                        model="fake",
                        objective="check_compatibility",
                        input_tokens=1,
                        output_tokens=1,
                        cost_usd=0.1,
                        cache={"key": "compat:fake", "hit": False},
                    ),
                )

        agent = SiteTaggedAgent()
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
        nodes = [
            tree.node(node_id) for node_id in tree.graph.nodes if node_id != "state_0"
        ]
        assert [node.candidate.site for node in nodes if node.candidate] == ["K5", "K6"]
        assert all(
            node.agent_result is not None
            and node.candidate is not None
            and node.agent_result.findings[0].affected == (node.candidate.site,)
            for node in nodes
        )
        winner_id = tree.surviving_ids[-1]
        verdict = RouteAssembler().assemble(
            request_id=request.request_id,
            validation=self._validation(request, bindings),
            tree=tree,
            post_graph=post_graph_report(request.request_id, selected_id=winner_id),
            families=CorpusRepository(self.families_path),
            judge=AgentResult(objective="final_judge", confidence="low"),
        )
        finding_affected = [
            token
            for conflict in verdict.conflicts
            if conflict.kind == "protecting_group_orthogonality"
            for token in conflict.affected
        ]
        assert finding_affected == ["K6"]
        assert finding_affected != ["K5"]

    def test_stage_siblings_all_expand(self, tmp_path: Path) -> None:
        request = self.request(
            request_id="T-PAR",
            sequence=GLUCAGON,
            modifications=[{"family": "lipidation", "site": "K12"}],
        )
        bindings = (
            self._binding(
                modification_ref=0,
                family=ModificationFamily.LIPIDATION,
                process_ids=(
                    "mtt_lipidation",
                    "ivdde_lipidation",
                    "alloc_lipidation",
                ),
                sheet="06_Lipidation",
            ),
        )
        walker, agent, _cache = self._walker(tmp_path)

        tree = walker.walk(request, self._validation(request, bindings))

        assert len(tree.surviving_ids) == 3
        assert len(agent.payloads) == 3

    def test_next_stage_waits_for_previous(self, tmp_path: Path) -> None:
        request = self.request(
            request_id="T-SEQ",
            sequence=GLUCAGON,
            modifications=[
                {"family": "special_residues", "site": "M27", "detail": "Met->Nle"},
                {"family": "lipidation", "site": "K12"},
            ],
        )
        bindings = (
            self._binding(
                modification_ref=0,
                family=ModificationFamily.SPECIAL_RESIDUES,
                process_ids=("p1",),
            ),
            self._binding(
                modification_ref=1,
                family=ModificationFamily.LIPIDATION,
                process_ids=("p2x", "p2y"),
            ),
        )
        events: list[tuple[str, str]] = []

        class OrderedAgent(ScriptedAgent):
            def invoke(self, payload: dict[str, Any]) -> AgentResult:
                process = str(payload["candidate"]["process"])
                events.append(("start", process))
                result = super().invoke(payload)
                events.append(("end", process))
                return result

        sandbox = LiteratureSandbox(tmp_path / "research")
        agent = OrderedAgent()
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

        walker.walk(request, self._validation(request, bindings))

        p1_end = next(
            index for index, event in enumerate(events) if event == ("end", "p1")
        )
        first_p2 = next(
            index
            for index, event in enumerate(events)
            if event[0] == "start" and event[1] in {"p2x", "p2y"}
        )
        assert p1_end < first_p2

    def test_walk_logs_stage_and_checks(self, tmp_path: Path, caplog: Any) -> None:
        caplog.set_level(logging.INFO, logger="route_agent.conflict")
        request = self.request(
            request_id="T-LOG",
            sequence=GLUCAGON,
            modifications=[{"family": "n_term_acetylation", "site": "N-term"}],
        )
        bindings = (
            self._binding(
                modification_ref=0,
                family=ModificationFamily.N_TERM_ACETYLATION,
                process_ids=("n_term_acetylation_default",),
            ),
        )
        walker, _agent, _cache = self._walker(tmp_path)

        walker.walk(request, self._validation(request, bindings))

        messages = [record.getMessage() for record in caplog.records]
        assert "walk_start" in messages
        assert "walk_stage_start" in messages
        assert "walk_check_start" in messages
        assert "walk_check_done" in messages
        assert "walk_complete" in messages

    def test_hung_check_is_marked_timeout_and_walk_continues(
        self, tmp_path: Path
    ) -> None:
        request = self.request(
            request_id="T-TO",
            sequence=GLUCAGON,
            modifications=[{"family": "lipidation", "site": "K12"}],
        )
        bindings = (
            self._binding(
                modification_ref=0,
                family=ModificationFamily.LIPIDATION,
                process_ids=("mtt_lipidation", "ivdde_lipidation"),
                sheet="06_Lipidation",
            ),
        )

        sandbox = LiteratureSandbox(tmp_path / "research")
        agent = SleepingOnProcessAgent("mtt_lipidation")
        runtime = AgentRuntime(
            sandbox=sandbox,
            tracer=FakeTracer(),
            logger=StructuredLogger(),
            agent=agent,
            cache=CompatCache(),
        )
        walker = ConflictWalker(
            runtime,
            CorpusRepository(self.families_path),
            check_timeout_s=5.0,
        )
        tree = walker.walk(request, self._validation(request, bindings))

        children = [tree.node(node_id) for node_id in tree.graph.successors("state_0")]
        statuses = {
            node.candidate.process: node.state.status
            for node in children
            if node.candidate is not None
        }
        unknowns = {
            node.candidate.process: node.agent_result.unknowns
            for node in children
            if node.candidate is not None and node.agent_result is not None
        }
        assert statuses["mtt_lipidation"] == "degraded"
        assert "check_timeout" in unknowns["mtt_lipidation"]
        assert statuses["ivdde_lipidation"] == "pass"
        assert tree.surviving_ids == tuple(
            node.state.id
            for node in children
            if node.candidate and node.candidate.process == "ivdde_lipidation"
        )

    def test_each_candidate_recomputes_protecting_groups_before_the_check(
        self, tmp_path: Path
    ) -> None:
        request = self.request(
            request_id="T-PG-WALK",
            sequence=GLUCAGON,
            modifications=[{"family": "lipidation", "site": "K12"}],
        )
        bindings = (
            self._binding(
                modification_ref=0,
                family=ModificationFamily.LIPIDATION,
                process_ids=(
                    "mtt_lipidation",
                    "ivdde_lipidation",
                    "alloc_lipidation",
                ),
                sheet="06_Lipidation",
            ),
        )
        observer = RecordingObserver()
        walker, agent, _cache = self._walker(tmp_path, observer=observer)

        tree = walker.walk(request, self._validation(request, bindings))
        children = [tree.node(node_id) for node_id in tree.graph.successors("state_0")]
        handles = {
            payload["candidate"]["process"]: payload["state"]["protected"]["K12"]
            for payload in agent.payloads
        }

        assert handles == {
            "mtt_lipidation": "Mtt",
            "ivdde_lipidation": "ivDde",
            "alloc_lipidation": "Alloc",
        }
        assert {node.state.output["protected"]["K12"] for node in children} == {
            "Mtt",
            "ivDde",
            "Alloc",
        }
        assert all(payload["prior"]["history"] == [] for payload in agent.payloads)
        assert all(payload["prior"]["resin"] == "Wang" for payload in agent.payloads)
        prepared = [
            event
            for event in observer.events
            if event.kind == "protecting_groups_prepared"
        ]
        assert [event.process for event in prepared] == [
            "mtt_lipidation",
            "ivdde_lipidation",
            "alloc_lipidation",
        ]
        assert prepared[0].diff is not None
        assert prepared[0].diff.protecting_groups["K12"] == "Mtt"

    def test_later_modification_sees_prior_operations_and_can_replace_handle(
        self, tmp_path: Path
    ) -> None:
        request = self.request(
            request_id="T-PG-REPLACE",
            sequence=GLUCAGON,
            modifications=[
                {"family": "lipidation", "site": "K12"},
                {"family": "pegylation", "site": "K12", "detail": "Fmoc-PEG8"},
            ],
        )
        bindings = (
            self._binding(
                modification_ref=0,
                family=ModificationFamily.LIPIDATION,
                process_ids=("alloc_lipidation",),
                sheet="06_Lipidation",
            ),
            self._binding(
                modification_ref=1,
                family=ModificationFamily.PEGYLATION,
                process_ids=("mtt_pegylation",),
            ),
        )
        walker, agent, _cache = self._walker(tmp_path)

        tree = walker.walk(request, self._validation(request, bindings))
        child = tree.node("state_1")
        grandchild = tree.node(next(iter(tree.graph.successors("state_1"))))
        second = agent.payloads[-1]

        assert child.state.output["protected"]["K12"] == "Alloc"
        assert grandchild.state.output["protected"]["K12"] == "Mtt"
        assert second["prior"]["history"][0]["process"] == "alloc_lipidation"
        assert second["state"]["protected"]["K12"] == "Mtt"
        assert second["prior"]["sequence_snapshot"] == GLUCAGON

    def test_future_branch_target_is_not_pending_during_earlier_stage(
        self, tmp_path: Path
    ) -> None:
        request = self.request(
            request_id="T-PG-FUTURE-WALK",
            sequence=GLUCAGON,
            modifications=[
                {"family": "n_term_acetylation", "site": "N-term"},
                {"family": "lipidation", "site": "K12"},
            ],
        )
        bindings = (
            self._binding(
                modification_ref=0,
                family=ModificationFamily.N_TERM_ACETYLATION,
                process_ids=("n_term_acetylation_default",),
            ),
            self._binding(
                modification_ref=1,
                family=ModificationFamily.LIPIDATION,
                process_ids=("alloc_lipidation",),
            ),
        )
        walker, agent, _cache = self._walker(tmp_path)

        walker.walk(request, self._validation(request, bindings))

        first = agent.payloads[0]
        second = agent.payloads[1]
        assert first["state"]["protected"]["K12"] == "Boc"
        assert second["state"]["protected"]["K12"] == "Alloc"
        assert second["prior"]["history"][0]["process"] == "n_term_acetylation_default"

    def test_unknown_residue_census_does_not_fail_the_node(
        self, tmp_path: Path
    ) -> None:
        request = self.request(
            request_id="T-PG-X",
            parent_name="octreotide",
            sequence=OCTREOTIDE,
            parent_c_terminus="alcohol",
            residue_annotations={"X8": "threoninol (Thr-ol)"},
            modifications=[{"family": "pegylation", "site": "K5"}],
        )
        bindings = (
            self._binding(
                modification_ref=0,
                family=ModificationFamily.PEGYLATION,
                process_ids=("pegylation_on_resin",),
            ),
        )
        walker, agent, _cache = self._walker(tmp_path)

        tree = walker.walk(request, self._validation(request, bindings))
        child = tree.node("state_1")

        assert agent.payloads
        assert child.state.status != "fail"
        assert child.agent_result is not None
        assert child.agent_result.passed is not False
        assert child.agent_result.findings == ()
        assert any(
            "no standard side-chain protecting" in item
            for item in child.agent_result.unknowns
        )
        assert tree.surviving_ids == ("state_1",)

    def test_uncapped_n_terminus_is_fmoc_during_on_resin_check(
        self, tmp_path: Path
    ) -> None:
        request = self.request(
            request_id="T-N-FMOC",
            sequence=GLUCAGON,
            modifications=[{"family": "lipidation", "site": "K12"}],
        )
        bindings = (
            self._binding(
                modification_ref=0,
                family=ModificationFamily.LIPIDATION,
                process_ids=("alloc_lipidation",),
                sheet="06_Lipidation",
            ),
        )
        walker, agent, _cache = self._walker(tmp_path)

        tree = walker.walk(request, self._validation(request, bindings))

        assert agent.payloads[0]["state"]["termini"]["n"] == "Fmoc"
        assert tree.node("state_1").state.output["termini"]["n"] == "Fmoc"

    def test_parent_n_terminal_acetyl_is_not_reset_to_fmoc(
        self, tmp_path: Path
    ) -> None:
        request = self.request(
            request_id="T-N-AC",
            sequence="SYSMEHFRWGKPV",
            parent_c_terminus="amide",
            parent_features=["N-terminal acetyl"],
            modifications=[{"family": "lipidation", "site": "K11"}],
        )
        bindings = (
            self._binding(
                modification_ref=0,
                family=ModificationFamily.LIPIDATION,
                process_ids=("alloc_lipidation",),
                sheet="06_Lipidation",
            ),
        )
        walker, agent, _cache = self._walker(tmp_path)
        validation = self._validation(request, bindings)
        validation.state.output["termini"] = {"n": "acetyl", "c": "amide"}

        walker.walk(request, validation)

        assert agent.payloads[0]["state"]["termini"]["n"] == "acetyl"

    def test_incompatible_candidate_is_pruned_with_recomputed_protecting_groups(
        self, tmp_path: Path
    ) -> None:
        request = self.request(
            request_id="T-PG-INCOMPAT",
            sequence=GLUCAGON,
            modifications=[{"family": "lipidation", "site": "K12"}],
        )
        bindings = (
            self._binding(
                modification_ref=0,
                family=ModificationFamily.LIPIDATION,
                process_ids=("alloc_lipidation", "mtt_lipidation"),
                sheet="06_Lipidation",
            ),
        )
        walker, agent, _cache = self._walker(
            tmp_path, outcomes={"alloc_lipidation": False}
        )

        tree = walker.walk(request, self._validation(request, bindings))
        children = [tree.node(node_id) for node_id in tree.graph.successors("state_0")]
        by_process = {
            node.candidate.process: node
            for node in children
            if node.candidate is not None
        }

        alloc = by_process["alloc_lipidation"]
        mtt = by_process["mtt_lipidation"]
        assert agent.payloads[0]["state"]["protected"]["K12"] == "Alloc"
        assert alloc.state.status == "fail"
        assert alloc.state.output["protected"]["K12"] == "Alloc"
        assert mtt.state.status == "pass"
        assert tree.surviving_ids == (mtt.state.id,)
