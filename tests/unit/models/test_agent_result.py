from __future__ import annotations

import pytest
from pydantic import ValidationError

from route_agent.models.agent import AgentResult


class TestAgentResult:
    def test_rejects_verdict_field(self) -> None:
        with pytest.raises(ValidationError, match="verdict"):
            AgentResult.model_validate(
                {
                    "objective": "check_compatibility",
                    "passed": True,
                    "verdict": "feasible",
                }
            )

    def test_compatibility_failure_may_name_same_site_resolution(self) -> None:
        result = AgentResult.model_validate(
            {
                "objective": "check_compatibility",
                "passed": False,
                "resolution": "ivdde_lipidation",
                "unknowns": (),
            }
        )

        assert result.passed is False
        assert result.resolution == "ivdde_lipidation"
        assert result.confidence is None

    def test_missing_objective_is_accepted_when_judgement_is_present(self) -> None:
        result = AgentResult.model_validate(
            {
                "passed": False,
                "findings": [
                    {
                        "kind": "reagent_incompatibility",
                        "description": "C-terminal amidation.",
                    }
                ],
            }
        )

        assert result.objective is None
        assert result.passed is False
        assert result.findings[0].kind == "reagent_incompatibility"

    def test_is_frozen(self) -> None:
        result = AgentResult(objective="check_intent", passed=None)
        with pytest.raises(ValidationError):
            result.passed = True

    def test_corpus_citation_without_ref_coerces_to_inference(self) -> None:
        result = AgentResult.model_validate(
            {
                "objective": "check_intent",
                "passed": True,
                "citations": [
                    {
                        "kind": "corpus",
                        "ref": None,
                        "basis": ("No target-specific SAR precedents are recorded."),
                    }
                ],
            }
        )
        assert result.citations[0].kind == "inference"
        assert result.citations[0].basis is not None
        assert "precedents are recorded" in result.citations[0].basis

    def test_corpus_citation_uses_refs_when_ref_missing(self) -> None:
        result = AgentResult.model_validate(
            {
                "objective": "check_intent",
                "passed": True,
                "citations": [
                    {
                        "kind": "corpus",
                        "refs": [
                            "ApexChem_Synthesis_Reactions_by_AminoAcid:06_Lipidation:8"
                        ],
                    }
                ],
            }
        )
        assert result.citations[0].kind == "corpus"
        assert result.citations[0].ref == (
            "ApexChem_Synthesis_Reactions_by_AminoAcid:06_Lipidation:8"
        )

    def test_type_adapter_accepts_corpus_without_ref(self) -> None:
        from pydantic import TypeAdapter

        result = TypeAdapter(AgentResult).validate_python(
            {
                "objective": "check_intent",
                "passed": True,
                "citations": [
                    {
                        "kind": "corpus",
                        "ref": None,
                        "basis": "glucagon_precedents are empty.",
                    }
                ],
            }
        )
        assert result.citations[0].kind == "inference"
        assert "precedents are empty" in (result.citations[0].basis or "")

    def test_prose_stuffed_into_corpus_ref_becomes_inference(self) -> None:
        result = AgentResult.model_validate(
            {
                "objective": "check_intent",
                "passed": True,
                "citations": [
                    {
                        "kind": "corpus",
                        "ref": "glucagon_precedents are empty.",
                    }
                ],
            }
        )
        assert result.citations[0].kind == "inference"
        assert result.citations[0].basis == "glucagon_precedents are empty."
