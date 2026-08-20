from __future__ import annotations

from route_agent.agent.runtime import build_prior_payload
from route_agent.conflict.handles import recompute_candidate_protection
from route_agent.models.agent import AgentCandidate
from route_agent.models.request import DesignRequest, Residue, ResolvedSite
from route_agent.parser.sequence import SequenceValidator
from route_agent.parser.sites import SiteValidator
from tests.support.validation_case import GLUCAGON, OCTREOTIDE, ValidationCase


class TestRecomputeCandidateProtection(ValidationCase):
    def _residues(self, request: DesignRequest) -> tuple[Residue, ...]:
        return (
            SequenceValidator()
            .validate_parent_sequence(request.sequence, request.residue_annotations)
            .residues
        )

    def _sites(self, request: DesignRequest) -> tuple[ResolvedSite, ...]:
        residues = self._residues(request)
        parsed = SiteValidator().validate_modification_sites(request, residues)
        return parsed.sites_resolved

    def test_rebuilds_from_census_then_applies_current_process(self) -> None:
        request = self.request(
            request_id="T-PG-ALLOC",
            sequence=GLUCAGON,
            modifications=[{"family": "lipidation", "site": "K12"}],
        )
        prior = build_prior_payload(
            {
                "history": [],
                "sequence_snapshot": GLUCAGON,
                "route_step": {"resin": "Wang"},
                "resin": "Wang",
            },
            request,
        )
        result = recompute_candidate_protection(
            residues=self._residues(request),
            sites=self._sites(request),
            request=request,
            prior=prior,
            candidate=AgentCandidate(
                family="lipidation", site="K12", process="alloc_lipidation"
            ),
        )

        assert result.ledger.protected["K12"] == "Alloc"
        assert result.ledger.protected["K12"] != "pending"
        assert result.ledger.protected["D9"] == "OtBu"
        assert result.errors == ()

    def test_replays_prior_history_before_current_process(self) -> None:
        request = self.request(
            request_id="T-PG-HISTORY",
            sequence=GLUCAGON,
            modifications=[
                {"family": "lipidation", "site": "K12"},
                {"family": "pegylation", "site": "K12", "detail": "Fmoc-PEG8"},
            ],
        )
        prior = build_prior_payload(
            {
                "history": [
                    {
                        "family": "lipidation",
                        "site": "K12",
                        "process": "alloc_lipidation",
                        "modification_ref": 0,
                        "passed": True,
                    }
                ],
                "sequence_snapshot": GLUCAGON,
                "resin": "Wang",
            },
            request,
        )
        result = recompute_candidate_protection(
            residues=self._residues(request),
            sites=self._sites(request),
            request=request,
            prior=prior,
            candidate=AgentCandidate(
                family="pegylation", site="K12", process="mtt_pegylation"
            ),
        )

        assert result.ledger.protected["K12"] == "Mtt"
        assert prior["history"][0]["process"] == "alloc_lipidation"

    def test_siblings_do_not_see_each_others_handles(self) -> None:
        request = self.request(
            request_id="T-PG-SIB",
            sequence=GLUCAGON,
            modifications=[{"family": "lipidation", "site": "K12"}],
        )
        prior = build_prior_payload({"history": [], "resin": "Wang"}, request)
        residues = self._residues(request)
        sites = self._sites(request)
        alloc = recompute_candidate_protection(
            residues=residues,
            sites=sites,
            request=request,
            prior=prior,
            candidate=AgentCandidate(
                family="lipidation", site="K12", process="alloc_lipidation"
            ),
        )
        mtt = recompute_candidate_protection(
            residues=residues,
            sites=sites,
            request=request,
            prior=prior,
            candidate=AgentCandidate(
                family="lipidation", site="K12", process="mtt_lipidation"
            ),
        )

        assert alloc.ledger.protected["K12"] == "Alloc"
        assert mtt.ledger.protected["K12"] == "Mtt"
        assert alloc.ledger.protected is not mtt.ledger.protected

    def test_future_branching_sites_keep_defaults_until_their_stage(self) -> None:
        request = self.request(
            request_id="T-PG-FUTURE",
            sequence=GLUCAGON,
            modifications=[
                {"family": "n_term_acetylation", "site": "N-term"},
                {"family": "lipidation", "site": "K12"},
            ],
        )
        prior = build_prior_payload({"history": [], "resin": "Wang"}, request)
        result = recompute_candidate_protection(
            residues=self._residues(request),
            sites=self._sites(request),
            request=request,
            prior=prior,
            candidate=AgentCandidate(
                family="n_term_acetylation",
                site="N-term",
                process="n_term_acetylation_default",
            ),
        )

        assert result.ledger.protected["K12"] == "Boc"
        assert "pending" not in result.ledger.protected.values()

    def test_unknown_residue_is_a_deterministic_error(self) -> None:
        request = self.request(
            request_id="T-PG-X",
            parent_name="octreotide",
            sequence=OCTREOTIDE,
            parent_c_terminus="alcohol",
            residue_annotations={"X8": "threoninol (Thr-ol)"},
            modifications=[{"family": "pegylation", "site": "K5"}],
        )
        prior = build_prior_payload({"history": []}, request)
        result = recompute_candidate_protection(
            residues=self._residues(request),
            sites=self._sites(request),
            request=request,
            prior=prior,
            candidate=AgentCandidate(
                family="pegylation", site="K5", process="pegylation_on_resin"
            ),
        )

        assert result.errors[0].code == "PROTECTING_GROUP_UNKNOWN"
        assert result.ledger.protected["K5"] == "pending"
