from __future__ import annotations

import json
from pathlib import Path

from route_agent.models.agent import AgentResult, CostReport
from route_agent.models.trace import PipelineTrace
from route_agent.models.verdict import RouteVerdict
from route_agent.trace import TraceWriter
from tests.support.conflict_fixtures import (
    empty_validation,
    make_tree,
    post_graph_report,
)
from tests.support.validation_case import ValidationCase


def _trace(request_id: str = "T-TRACE") -> PipelineTrace:
    request = ValidationCase().request(request_id=request_id)
    validation = empty_validation(request_id)
    tree = make_tree([], [], surviving_ids=())
    return PipelineTrace(
        request_id=request_id,
        request=request,
        validation=validation,
        tree=tree.to_report(request_id),
        post_graph=post_graph_report(request_id, selected_id=None),
        judge=AgentResult(objective="final_judge", confidence="low"),
        verdict=RouteVerdict(
            request_id=request_id,
            verdict="insufficient_information",
            confidence="low",
            resolved_sequence="ACDEK",
            resolved_annotations={},
            site_map=validation.site_map,
            route=(),
            conflicts=(),
            unknowns=("no winning candidate",),
        ),
        cost=CostReport(),
        llm_calls=(),
    )


class TestTraceWriter:
    def test_writes_atomic_trace_named_by_request_id(self, tmp_path: Path) -> None:
        writer = TraceWriter(tmp_path / "traces")
        path = writer.write(_trace("REQ-09"))
        assert path == tmp_path / "traces" / "REQ-09.trace.json"
        assert path.is_file()
        payload = path.read_text(encoding="utf-8")
        assert '"request_id": "REQ-09"' in payload
        assert '"validation"' in payload
        assert '"tree"' in payload
        assert '"post_graph"' in payload
        assert '"judge"' in payload
        assert '"verdict"' in payload
        assert '"cost"' in payload
        leftover = list((tmp_path / "traces").glob("*.tmp"))
        assert leftover == []

    def test_writes_run_and_job_ids(self, tmp_path: Path) -> None:
        writer = TraceWriter(tmp_path / "traces")
        path = writer.write(
            _trace("REQ-10").model_copy(update={"run_id": "run-1", "job_id": "job-1"})
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["run_id"] == "run-1"
        assert payload["job_id"] == "job-1"
        assert payload["trace_version"] == 3

    def test_reads_legacy_trace_without_correlation_ids(self, tmp_path: Path) -> None:
        writer = TraceWriter(tmp_path / "traces")
        path = writer.write(_trace("REQ-11"))
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload.pop("run_id", None)
        payload.pop("job_id", None)
        payload.pop("trace_version", None)
        legacy = PipelineTrace.model_validate(payload)
        assert legacy.run_id is None
        assert legacy.job_id is None
        assert legacy.trace_version == 3
        assert legacy.request_id == "REQ-11"
