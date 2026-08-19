from __future__ import annotations

from route_agent.models.molecular import (
    CandidatePostGraphResult,
    PostGraphValidationReport,
)
from route_agent.post_graph.intent import intent_rank


def select_winning_candidate(
    *,
    request_id: str,
    surviving_ids: tuple[str, ...],
    candidates: tuple[CandidatePostGraphResult, ...],
) -> PostGraphValidationReport:
    ranked = sorted(candidates, key=lambda item: (ranking_key(item), item.node_id))
    valid = [item for item in ranked if item.molecular.two_d.valid]
    unknowns: list[str] = []
    for item in candidates:
        unknowns.extend(item.molecular.unknowns)
        if item.intent is not None:
            unknowns.extend(item.intent.unknowns)
    if not valid:
        unknowns.append("no 2D-valid candidate")
        return PostGraphValidationReport(
            request_id=request_id,
            surviving_ids=surviving_ids,
            selected_id=None,
            tied_ids=(),
            unknowns=tuple(dict.fromkeys(unknowns)),
            candidates=candidates,
        )
    best_key = ranking_key(valid[0])
    tied = tuple(item.node_id for item in valid if ranking_key(item) == best_key)
    if len(tied) > 1:
        unknowns.append("tied_candidates:" + ",".join(tied))
    return PostGraphValidationReport(
        request_id=request_id,
        surviving_ids=surviving_ids,
        selected_id=tied[0],
        tied_ids=tied[1:],
        unknowns=tuple(dict.fromkeys(unknowns)),
        candidates=candidates,
    )


def ranking_key(result: CandidatePostGraphResult) -> tuple[int, ...]:
    molecular = result.molecular
    two_d = 0 if molecular.two_d.valid else 1
    intent = intent_rank(result.intent)
    ensemble = molecular.ensemble
    embed = 0 if ensemble is not None and ensemble.embedding_ok else 1
    converged = 0 if ensemble is not None and ensemble.converged else 1
    clashes = ensemble.n_clashes if ensemble is not None else 10_000
    return (two_d, intent, embed, converged, clashes)
