from __future__ import annotations

from route_agent.models.agent import AgentCandidate, AgentFinding, AgentResult
from route_agent.models.molecular import (
    CandidateMolecularValidation,
    CandidatePostGraphResult,
    ConformerEnsemble,
    TwoDValidation,
)
from route_agent.post_graph.intent import keep_intent_findings_only
from route_agent.post_graph.selector import select_winning_candidate


def _molecular(
    node_id: str,
    *,
    valid: bool,
    embedding_ok: bool = True,
    converged: bool = True,
    clashes: int = 0,
) -> CandidateMolecularValidation:
    return CandidateMolecularValidation(
        node_id=node_id,
        two_d=TwoDValidation(
            valid=valid,
            formula="C2H5NO2" if valid else None,
            exact_mw=75.03 if valid else None,
        ),
        ensemble=ConformerEnsemble(
            embedding_ok=embedding_ok,
            converged=converged,
            n_requested=2,
            n_embedded=2 if embedding_ok else 0,
            n_optimized=2 if converged else 0,
            valid_fraction=1.0 if embedding_ok else 0.0,
            forcefield="MMFF94s",
            n_clashes=clashes,
        ),
    )


def _candidate(
    node_id: str,
    *,
    valid: bool = True,
    passed: bool | None = True,
    intent_fail: bool = False,
    extra_finding: bool = False,
    embedding_ok: bool = True,
    clashes: int = 0,
) -> CandidatePostGraphResult:
    findings = []
    if intent_fail:
        findings.append(
            AgentFinding(
                kind="intent_not_achieved",
                description="hits the pharmacophore",
                affected=("K5",),
            )
        )
    if extra_finding:
        findings.append(
            AgentFinding(
                kind="reagent_incompatibility", description="should be dropped"
            )
        )
    intent = AgentResult(
        objective="check_intent",
        passed=False if intent_fail else passed,
        findings=tuple(findings),
    )
    intent = keep_intent_findings_only(intent)
    return CandidatePostGraphResult(
        node_id=node_id,
        candidate=AgentCandidate(family="lipidation", site="K5", process=node_id),
        molecular=_molecular(
            node_id, valid=valid, embedding_ok=embedding_ok, clashes=clashes
        ),
        intent=intent if valid else None,
    )


class TestSelector:
    def test_invalid_2d_cannot_win(self) -> None:
        report = select_winning_candidate(
            request_id="T-GATE",
            surviving_ids=("state_1", "state_2"),
            candidates=(
                _candidate("state_1", valid=False, passed=True),
                _candidate("state_2", valid=True, passed=True),
            ),
        )
        assert report.selected_id == "state_2"
        assert "verdict" not in report.model_dump()

    def test_intent_outranks_3d_quality(self) -> None:
        report = select_winning_candidate(
            request_id="T-INTENT",
            surviving_ids=("state_1", "state_2"),
            candidates=(
                _candidate("state_1", intent_fail=True, clashes=0),
                _candidate("state_2", passed=True, clashes=9),
            ),
        )
        assert report.selected_id == "state_2"

    def test_3d_breaks_intent_tie(self) -> None:
        report = select_winning_candidate(
            request_id="T-3D",
            surviving_ids=("state_1", "state_2"),
            candidates=(
                _candidate("state_1", passed=True, clashes=4),
                _candidate("state_2", passed=True, clashes=0),
            ),
        )
        assert report.selected_id == "state_2"

    def test_genuine_tie_is_recorded(self) -> None:
        report = select_winning_candidate(
            request_id="T-TIE",
            surviving_ids=("state_2", "state_1"),
            candidates=(
                _candidate("state_2", passed=True, clashes=0),
                _candidate("state_1", passed=True, clashes=0),
            ),
        )
        assert report.selected_id in {"state_1", "state_2"}
        assert report.tied_ids
        assert any(item.startswith("tied_candidates:") for item in report.unknowns)

    def test_no_valid_candidate(self) -> None:
        report = select_winning_candidate(
            request_id="T-NONE",
            surviving_ids=("state_1",),
            candidates=(_candidate("state_1", valid=False),),
        )
        assert report.selected_id is None
        assert "no 2D-valid candidate" in report.unknowns

    def test_non_intent_findings_are_dropped(self) -> None:
        candidate = _candidate("state_1", passed=True, extra_finding=True)
        assert candidate.intent is not None
        assert candidate.intent.findings == ()
        assert any(
            "dropped_non_intent_findings" in item for item in candidate.intent.unknowns
        )
