from __future__ import annotations

from pathlib import Path

from route_agent.composition.wiring import (
    build_agent_runtime,
    build_parser,
    build_route_pipeline,
    build_tracer,
    first_candidate_from_request,
    objective_from_name,
)
from route_agent.conflict import ConflictWalker
from route_agent.observability import StructuredLogger
from route_agent.parser.request_parser import RequestParser
from route_agent.pipeline import RoutePipeline
from route_agent.post_graph.validator import PostGraphValidator
from route_agent.settings import Settings
from tests.support.validation_case import ValidationCase


class TestWiring(ValidationCase):
    def test_build_parser_no_model_returns_request_parser(self) -> None:
        parser = build_parser(Settings(no_model=True), logger=StructuredLogger())
        assert isinstance(parser, RequestParser)

    def test_build_agent_runtime_no_model_skips_deep_agent(self) -> None:
        runtime, _families = build_agent_runtime(
            Settings(no_model=True), logger=StructuredLogger()
        )
        assert runtime._enabled is False
        assert runtime._agent is None

    def test_build_route_pipeline_no_model_wires_walker_and_post_graph(
        self, tmp_path: Path
    ) -> None:
        pipeline = build_route_pipeline(
            Settings(no_model=True), StructuredLogger(), tmp_path
        )
        assert isinstance(pipeline, RoutePipeline)
        assert isinstance(pipeline._walker, ConflictWalker)
        assert isinstance(pipeline._post_graph, PostGraphValidator)
        assert pipeline._tracer is build_tracer(Settings(no_model=True))

    def test_build_tracer_reuses_the_same_instance_for_the_same_keys(self) -> None:
        settings = Settings(no_model=True)
        assert build_tracer(settings) is build_tracer(settings)

    def test_first_candidate_uses_bound_process_id(self) -> None:
        request = self.request(
            request_id="T-WIRE",
            sequence="ACDEK",
            modifications=[{"family": "lipidation", "site": "K5"}],
        )
        _runtime, families = build_agent_runtime(
            Settings(no_model=True), logger=StructuredLogger()
        )
        candidate = first_candidate_from_request(request, families)
        assert candidate.family == "lipidation"
        assert candidate.site == "K5"
        assert candidate.process

    def test_objective_from_name_keeps_literal(self) -> None:
        assert objective_from_name("check_intent") == "check_intent"
