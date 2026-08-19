from __future__ import annotations

from route_agent.models.agent import LLMCall, build_cost_report


def _call(
    *,
    objective: str,
    cost_usd: float,
    stage: str | None = None,
    input_tokens: int = 10,
    output_tokens: int = 5,
    hit: bool = False,
) -> LLMCall:
    return LLMCall(
        call_id=f"llm_{objective}",
        model="fake",
        objective=objective,  # type: ignore[arg-type]
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        cache={"key": objective, "hit": hit},
        stage=stage,  # type: ignore[arg-type]
    )


class TestCostReport:
    def test_phase_totals_sum_to_grand_total(self) -> None:
        report = build_cost_report(
            (
                _call(objective="structure_request", cost_usd=0.10, stage="validate"),
                _call(objective="check_compatibility", cost_usd=0.20, stage="walk"),
                _call(objective="check_intent", cost_usd=0.05, stage="post_graph"),
            )
        )

        assert report.total.cost_usd == 0.35
        assert report.total.calls == 3
        assert report.phases["validate"].cost_usd == 0.10
        assert report.phases["walk"].cost_usd == 0.20
        assert report.phases["post_graph"].cost_usd == 0.05
        phase_sum = round(sum(item.cost_usd for item in report.phases.values()), 8)
        assert phase_sum == report.total.cost_usd
        assert report.objectives["check_compatibility"].calls == 1

    def test_cache_hit_contributes_zero_cost(self) -> None:
        report = build_cost_report(
            (
                _call(
                    objective="check_compatibility",
                    cost_usd=0.0,
                    stage="walk",
                    input_tokens=0,
                    output_tokens=0,
                    hit=True,
                ),
            )
        )

        assert report.total.cost_usd == 0.0
        assert report.total.calls == 1
        assert report.phases["walk"].calls == 1
