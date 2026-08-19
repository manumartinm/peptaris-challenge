from __future__ import annotations

from pathlib import Path
from typing import Any

from route_agent.models.agent import AgentResult, LLMCall
from route_agent.models.request import DesignRequest
from route_agent.models.verdict import RouteVerdict
from route_agent.pipeline import RoutePipeline
from route_agent.trace import TraceWriter
from route_agent.verdict.assembler import RouteAssembler
from tests.support.cli import PUBLIC_VERDICT_FIELDS
from tests.support.conflict_fixtures import (
    empty_validation,
    lipid_candidate,
    make_node,
    make_tree,
    post_graph_report,
    resin_node,
)
from tests.support.score import validate_schema
from tests.support.validation_case import ValidationCase


class ScriptedParser:
    def __init__(self, validation: Any) -> None:
        self.validation = validation
        self.calls: list[DesignRequest] = []

    def run_validation_pipeline(self, request: DesignRequest) -> Any:
        self.calls.append(request)
        return self.validation


class ScriptedWalker:
    def __init__(self, tree: Any) -> None:
        self.tree = tree
        self.calls = 0

    def walk(self, request: DesignRequest, validation: Any) -> Any:
        self.calls += 1
        return self.tree


class ScriptedPostGraph:
    def __init__(self, report: Any) -> None:
        self.report = report
        self.calls = 0

    def validate(self, request: DesignRequest, validation: Any, tree: Any) -> Any:
        self.calls += 1
        return self.report


class ScriptedJudge:
    def __init__(self, result: AgentResult) -> None:
        self.result = result
        self.calls = 0

    def run(
        self,
        request: DesignRequest,
        validation: Any,
        tree: Any,
        post_graph: Any,
        route_draft: Any,
    ) -> AgentResult:
        self.calls += 1
        return self.result


class TestRoutePipeline(ValidationCase):
    def _tree(self) -> Any:
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

    def test_runs_stages_once_and_writes_internal_trace(self, tmp_path: Path) -> None:
        request = self.request(request_id="T-PIPE")
        validation = empty_validation("T-PIPE")
        tree = self._tree()
        post_graph = post_graph_report(
            "T-PIPE", selected_id="state_1", surviving_ids=("state_1",)
        )
        judge = AgentResult(
            objective="final_judge",
            confidence="medium",
            llm_call=LLMCall(
                call_id="llm_final_judge",
                model="fake",
                objective="final_judge",
                input_tokens=11,
                output_tokens=7,
                cost_usd=0.02,
                cache={"key": "final_judge", "hit": False},
            ),
        )
        parser = ScriptedParser(validation)
        walker = ScriptedWalker(tree)
        post = ScriptedPostGraph(post_graph)
        judge_runner = ScriptedJudge(judge)
        pipeline = RoutePipeline(
            parser=parser,
            walker=walker,
            post_graph=post,
            judge=judge_runner,
            assembler=RouteAssembler(),
            families=object(),
            traces=TraceWriter(tmp_path / "traces"),
        )

        result = pipeline.run(request)

        assert parser.calls == [request]
        assert walker.calls == 1
        assert post.calls == 1
        assert judge_runner.calls == 1
        assert isinstance(result.verdict, RouteVerdict)
        dumped = result.verdict.model_dump(mode="json")
        assert set(dumped) == PUBLIC_VERDICT_FIELDS
        schema = validate_schema(dumped, tmp_path)
        assert schema["invalid"] == []
        assert result.trace_path == tmp_path / "traces" / "T-PIPE.trace.json"
        assert result.trace_path is not None
        trace = result.trace_path.read_text(encoding="utf-8")
        assert '"tree"' in trace
        assert '"judge"' in trace
        assert '"cost"' in trace
        assert result.cost.total.calls >= 1
        assert "cost" not in dumped
        assert "tree" not in dumped

    def test_single_langfuse_root_and_stage_spans(self, tmp_path: Path) -> None:
        from tests.support.fake_tracer import FakeTracer

        request = self.request(request_id="T-TRACE-ROOT")
        tracer = FakeTracer()
        pipeline = RoutePipeline(
            parser=ScriptedParser(empty_validation("T-TRACE-ROOT")),
            walker=ScriptedWalker(self._tree()),
            post_graph=ScriptedPostGraph(
                post_graph_report(
                    "T-TRACE-ROOT", selected_id="state_1", surviving_ids=("state_1",)
                )
            ),
            judge=ScriptedJudge(AgentResult(objective="final_judge", confidence="low")),
            assembler=RouteAssembler(),
            families=object(),
            traces=TraceWriter(tmp_path / "traces"),
            tracer=tracer,
        )

        result = pipeline.run(request)

        assert len(tracer.runs) == 1
        assert tracer.runs[0]["request_id"] == "T-TRACE-ROOT"
        assert [item["name"] for item in tracer.spans] == [
            "validation_engine",
            "walk",
            "post_graph",
            "final_judge",
        ]
        assert result.trace.run_id
        assert result.trace.trace_version == 3
        kinds = [event.kind for event in result.trace.events]
        assert kinds.count("stage_started") >= 4
        assert kinds.count("stage_finished") >= 4
