from __future__ import annotations

from pathlib import Path

from route_agent.models.trace import PipelineTrace


class TraceWriter:
    def __init__(self, trace_dir: Path) -> None:
        self._trace_dir = trace_dir

    def write(self, trace: PipelineTrace) -> Path:
        self._trace_dir.mkdir(parents=True, exist_ok=True)
        target = self._trace_dir / f"{trace.request_id}.trace.json"
        tmp = self._trace_dir / f".{trace.request_id}.trace.json.tmp"
        tmp.write_text(trace.model_dump_json(indent=2) + "\n", encoding="utf-8")
        tmp.replace(target)
        return target
