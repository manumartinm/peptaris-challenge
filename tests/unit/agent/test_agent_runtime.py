from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from route_agent.agent.runtime import AgentRuntime, CompatCache
from route_agent.corpus import CorpusRepository
from route_agent.literature.sandbox import LiteratureSandbox
from route_agent.models.agent import AgentCandidate, AgentResult, LLMCall
from route_agent.observability import StructuredLogger
from tests.support.fake_tracer import FakeTracer
from tests.support.validation_case import ValidationCase


class FakeDeepAgent:
    def __init__(self, sandbox: LiteratureSandbox) -> None:
        self.sandbox = sandbox
        self.payloads: list[dict[str, Any]] = []

    def invoke(self, payload: dict[str, Any]) -> AgentResult:
        self.payloads.append(payload)
        request_id = str(payload["request_id"])
        self.sandbox.write_memory(request_id, "notes.md", "Alloc vs Trt noted.\n")
        return AgentResult(
            objective=payload["objective"],
            passed=True,
            llm_call=LLMCall(
                call_id="llm_check_compatibility",
                model="fake",
                objective=payload["objective"],
                input_tokens=1,
                output_tokens=1,
                cost_usd=0.0,
                cache={"key": "compat:fake", "hit": False},
            ),
        )


class TestAgentRuntime(ValidationCase):
    def make_runtime(
        self,
        tmp_path: Path,
        enabled: bool = True,
        families: CorpusRepository | None = None,
    ) -> tuple[AgentRuntime, FakeDeepAgent, FakeTracer, LiteratureSandbox]:
        sandbox = LiteratureSandbox(tmp_path / "research")
        agent = FakeDeepAgent(sandbox)
        tracer = FakeTracer()
        runtime = AgentRuntime(
            sandbox=sandbox,
            tracer=tracer,
            logger=StructuredLogger(),
            agent=agent,
            enabled=enabled,
            cache=CompatCache(),
            families=families,
        )
        return runtime, agent, tracer, sandbox

    def test_second_invoke_sees_memory_notes(self, tmp_path: Path) -> None:
        runtime, agent, tracer, sandbox = self.make_runtime(tmp_path)
        request = self.request(
            request_id="REQ-MEM",
            sequence="ACDEK",
            modifications=[{"family": "lipidation", "site": "K5"}],
        )
        candidate = AgentCandidate(
            family="lipidation", site="K5", process="alloc_lipidation"
        )
        payload = {
            "protected": {"K5": "pending"},
            "free_amines": {},
            "catalysts_used": {},
            "termini": {"c": "amide"},
        }

        first = runtime.invoke("check_compatibility", request, payload, candidate)
        second = runtime.invoke("check_intent", request, payload, candidate)

        assert first.passed is True
        assert second.objective == "check_intent"
        assert [event["name"] for event in tracer.spans] == [
            "agent/check_compatibility",
            "agent/check_intent",
        ]
        assert "memory/REQ-MEM/notes.md" in sandbox.list_files("")
        assert "Alloc" in sandbox.read_file("memory/REQ-MEM/notes.md")
        assert len(agent.payloads) == 2
        assert "process_profile" in agent.payloads[0]
        assert "prior" in agent.payloads[0]

    def test_parent_name_lookup_is_injected_into_payload(self, tmp_path: Path) -> None:
        runtime, agent, _tracer, _sandbox = self.make_runtime(
            tmp_path,
            families=CorpusRepository(
                self.families_path,
                targets_path=self.data_dir / "ApexChem_templates_and_targets.xlsx",
            ),
        )
        request = self.request(
            request_id="REQ-09",
            parent_name="glucagon",
            sequence="ACDEK",
            modifications=[{"family": "c_term_amidation", "site": "C-term"}],
        )
        runtime.invoke(
            "check_compatibility",
            request,
            {"protected": {}, "termini": {"c": "free_acid"}},
            AgentCandidate(
                family="c_term_amidation",
                site="C-term",
                process="c_term_amidation_default",
            ),
        )

        target = agent.payloads[0]["parent_target"]
        assert target["available"] is True
        assert target["peptide"] == "Glucagon"
        assert target["receptor_class"] == "GPCR class B1"
        assert target["ligand_role"] == "agonist"
        assert "Glucagon" in (target["receptor_target"] or "")

    def test_check_intent_receives_molecular_context(self, tmp_path: Path) -> None:
        runtime, agent, _tracer, _sandbox = self.make_runtime(tmp_path)
        request = self.request(
            request_id="REQ-INTENT",
            sequence="ACDEK",
            modifications=[{"family": "lipidation", "site": "K5"}],
        )
        runtime.invoke(
            "check_intent",
            request,
            {"resolved_sequence": "ACDEK", "termini": {"c": "amide"}},
            AgentCandidate(family="lipidation", site="K5", process="alloc_lipidation"),
            context={
                "molecular_validation": {
                    "valid": True,
                    "formula": "C10H18N2O3",
                    "exact_mw": 230.13,
                    "ph": 7.4,
                    "net_charge": 0.1,
                },
                "ensemble_3d": {"embedding_ok": True, "n_clashes": 0},
            },
        )

        payload = agent.payloads[0]
        assert payload["objective"] == "check_intent"
        assert payload["resolved_sequence"] == "ACDEK"
        assert payload["candidate_process"] == "alloc_lipidation"
        assert payload["parent_peptide"] == "test"
        assert payload["molecular_validation"]["formula"] == "C10H18N2O3"
        assert payload["ensemble_3d"]["embedding_ok"] is True

    def test_disabled_runtime_does_not_call_agent(self, tmp_path: Path) -> None:
        runtime, agent, _tracer, _sandbox = self.make_runtime(tmp_path, enabled=False)
        request = self.request(
            request_id="REQ-OFF",
            sequence="ACDEK",
            modifications=[{"family": "lipidation", "site": "K5"}],
        )
        result = runtime.invoke(
            "check_compatibility",
            request,
            {"protected": {}},
            AgentCandidate(family="lipidation", site="K5", process="mtt_lipidation"),
        )

        assert agent.payloads == []
        assert result.passed is None
        assert result.unknowns
        assert result.objective == "check_compatibility"

    def test_compat_cache_skips_second_identical_call(self, tmp_path: Path) -> None:
        runtime, agent, _tracer, _sandbox = self.make_runtime(tmp_path)
        request = self.request(
            request_id="REQ-CACHE",
            sequence="ACDEK",
            modifications=[{"family": "lipidation", "site": "K5"}],
        )
        candidate = AgentCandidate(
            family="lipidation", site="K5", process="alloc_lipidation"
        )
        state = {
            "protected": {"C2": "Trt"},
            "free_amines": {},
            "catalysts_used": {},
            "termini": {},
        }

        first = runtime.invoke("check_compatibility", request, state, candidate)
        second = runtime.invoke("check_compatibility", request, state, candidate)

        assert first.passed is True
        assert second.llm_call is not None
        assert second.llm_call.cache["hit"] is True
        assert second.llm_call.cost_usd == 0.0
        assert second.llm_call.input_tokens == 0
        assert second.llm_call.output_tokens == 0
        assert len(agent.payloads) == 1

    def test_compat_cache_hits_equivalent_protecting_groups(
        self, tmp_path: Path
    ) -> None:
        runtime, agent, _tracer, _sandbox = self.make_runtime(tmp_path)
        request = self.request(
            request_id="REQ-EQ",
            sequence="ACDEK",
            modifications=[{"family": "lipidation", "site": "K5"}],
        )
        candidate = AgentCandidate(
            family="lipidation", site="K5", process="alloc_lipidation"
        )
        first = runtime.invoke(
            "check_compatibility",
            request,
            {"protected": {"K5": "Trt"}},
            candidate,
        )
        second = runtime.invoke(
            "check_compatibility",
            request,
            {"protected": {"K5": "Mtt"}},
            candidate,
        )

        assert first.passed is True
        assert second.llm_call is not None
        assert second.llm_call.cache["hit"] is True
        assert len(agent.payloads) == 1

    def test_compat_cache_evicts_oldest_entry(self, tmp_path: Path) -> None:
        sandbox = LiteratureSandbox(tmp_path / "research")
        agent = FakeDeepAgent(sandbox)
        runtime = AgentRuntime(
            sandbox=sandbox,
            tracer=FakeTracer(),
            logger=StructuredLogger(),
            agent=agent,
            cache=CompatCache(max_entries=2),
        )
        request = self.request(
            request_id="REQ-LRU",
            sequence="ACDEK",
            modifications=[{"family": "lipidation", "site": "K5"}],
        )
        for process in ("p1", "p2", "p3"):
            runtime.invoke(
                "check_compatibility",
                request,
                {"protected": {"K5": "Trt"}},
                AgentCandidate(family="lipidation", site="K5", process=process),
            )
        runtime.invoke(
            "check_compatibility",
            request,
            {"protected": {"K5": "Trt"}},
            AgentCandidate(family="lipidation", site="K5", process="p1"),
        )

        assert len(agent.payloads) == 4

    def test_compat_cache_hit_does_not_emit_generation(self, tmp_path: Path) -> None:
        runtime, agent, tracer, _sandbox = self.make_runtime(tmp_path)
        request = self.request(
            request_id="REQ-NOGEN",
            sequence="ACDEK",
            modifications=[{"family": "lipidation", "site": "K5"}],
        )
        candidate = AgentCandidate(
            family="lipidation", site="K5", process="alloc_lipidation"
        )
        state = {"protected": {"K5": "Alloc"}}
        runtime.invoke("check_compatibility", request, state, candidate)
        runtime.invoke("check_compatibility", request, state, candidate)

        assert len(agent.payloads) == 1
        assert tracer.generations == []

    def test_compat_cache_does_not_collide_across_sites(self, tmp_path: Path) -> None:
        runtime, agent, _tracer, _sandbox = self.make_runtime(tmp_path)
        request = self.request(
            request_id="REQ-SITES",
            sequence="ACDEK",
            modifications=[{"family": "lipidation", "site": "K5"}],
        )
        first = runtime.invoke(
            "check_compatibility",
            request,
            {"protected": {"K5": "Trt"}},
            AgentCandidate(family="lipidation", site="K5", process="alloc_lipidation"),
        )
        second = runtime.invoke(
            "check_compatibility",
            request,
            {"protected": {"K12": "Trt"}},
            AgentCandidate(family="lipidation", site="K12", process="alloc_lipidation"),
        )

        assert first.passed is True
        assert second.llm_call is not None
        assert second.llm_call.cache.get("hit") is not True
        assert len(agent.payloads) == 2

    def test_compat_cache_does_not_collide_across_product_topology(
        self, tmp_path: Path
    ) -> None:
        runtime, agent, _tracer, _sandbox = self.make_runtime(tmp_path)
        request = self.request(
            request_id="REQ-TOPO",
            sequence="ACDEK",
            modifications=[{"family": "lipidation", "site": "K5"}],
        )
        candidate = AgentCandidate(
            family="lipidation", site="K5", process="alloc_lipidation"
        )
        ledger = {
            "protected": {"K5": "Alloc"},
            "free_amines": {},
            "catalysts_used": {},
            "termini": {"n": "free", "c": "acid"},
            "history": [{"process": "p1"}],
        }
        first = runtime.invoke(
            "check_compatibility",
            request,
            {
                **ledger,
                "permanent_connectivity": [
                    {
                        "from_atom": "C2.SG",
                        "to_fragment": "C7.SG",
                        "bond_type": "disulfide",
                    }
                ],
            },
            candidate,
        )
        second = runtime.invoke(
            "check_compatibility",
            request,
            {
                **ledger,
                "permanent_connectivity": [
                    {"from_atom": "K5.NZ", "to_fragment": "c16:1", "bond_type": "amide"}
                ],
            },
            candidate,
        )

        assert first.passed is True
        assert second.llm_call is not None
        assert second.llm_call.cache.get("hit") is not True
        assert len(agent.payloads) == 2

    def test_business_exception_propagates_from_agent(self, tmp_path: Path) -> None:
        sandbox = LiteratureSandbox(tmp_path / "research")

        class BoomAgent:
            def invoke(self, payload: dict[str, Any]) -> AgentResult:
                raise RuntimeError(f"boom:{payload['request_id']}")

        runtime = AgentRuntime(
            sandbox=sandbox,
            tracer=FakeTracer(),
            logger=StructuredLogger(),
            cache=CompatCache(),
            agent=BoomAgent(),
        )
        request = self.request(
            request_id="T-RAISE",
            sequence="ACDEK",
            modifications=[{"family": "lipidation", "site": "K5"}],
        )

        with pytest.raises(RuntimeError, match="boom:T-RAISE"):
            runtime.invoke(
                "check_compatibility",
                request,
                {"protected": {}},
                AgentCandidate(
                    family="lipidation", site="K5", process="alloc_lipidation"
                ),
            )
