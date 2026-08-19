"""Render ``--explain`` progress on stderr without touching stdout JSON."""

from __future__ import annotations

import sys
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any, TextIO

from route_agent.models.events import PipelineEvent, StateDiff
from route_agent.observe import PipelineObserver

_STATUS_MARK = {"pass": "ok", "fail": "fail", "degraded": "degraded"}


@dataclass
class ExplainState:
    stage: str = "idle"
    request_id: str | None = None
    nodes: dict[str, str] = field(default_factory=dict)
    frontier: tuple[str, ...] = ()
    last_diff: str = ""
    last_message: str = ""
    calls: int = 0
    cost_usd: float = 0.0
    lines: list[str] = field(default_factory=list)


class PlainTextObserver:
    """Append-only renderer for pipes, CI, and terminals without color."""

    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream or sys.stderr
        self.state = ExplainState()

    def on_event(self, event: PipelineEvent) -> None:
        line = format_event_line(event)
        self.state = apply_event(self.state, event)
        self.state.lines.append(line)
        print(line, file=self._stream)

    def close(self) -> None:
        return None


class RichLiveObserver:
    """Live dashboard for an interactive color terminal."""

    def __init__(self) -> None:
        from rich.console import Console
        from rich.live import Live

        self.state = ExplainState()
        self._console = Console(stderr=True, highlight=False)
        self._live = Live(
            self._render(),
            console=self._console,
            refresh_per_second=8,
            transient=False,
        )
        self._live.start()

    def on_event(self, event: PipelineEvent) -> None:
        self.state = apply_event(self.state, event)
        self.state.lines.append(format_event_line(event))
        self._live.update(self._render())

    def close(self) -> None:
        with suppress(Exception):
            self._live.stop()

    def _render(self) -> Any:
        from rich.panel import Panel
        from rich.table import Table
        from rich.text import Text

        table = Table.grid(padding=(0, 1))
        table.add_row("stage", self.state.stage)
        if self.state.request_id:
            table.add_row("request", self.state.request_id)
        table.add_row("frontier", ", ".join(self.state.frontier) or "—")
        table.add_row(
            "last change", self.state.last_diff or self.state.last_message or "—"
        )
        table.add_row(
            "cost",
            f"${self.state.cost_usd:.4f}  calls={self.state.calls}",
        )
        if self.state.nodes:
            tree = Text()
            for node_id, label in self.state.nodes.items():
                tree.append(f"{node_id}  {label}\n")
            table.add_row("tree", tree)
        return Panel(table, title="route-agent", border_style="cyan")


def build_explain_observer(*, interactive: bool | None = None) -> PipelineObserver:
    use_rich = sys.stderr.isatty() if interactive is None else interactive
    if use_rich:
        try:
            return RichLiveObserver()
        except Exception:
            return PlainTextObserver()
    return PlainTextObserver()


def apply_event(state: ExplainState, event: PipelineEvent) -> ExplainState:
    nodes = dict(state.nodes)
    if event.node_id:
        nodes[event.node_id] = _node_label(event)
    return ExplainState(
        stage=event.stage,
        request_id=event.request_id or state.request_id,
        nodes=nodes,
        frontier=event.frontier or state.frontier,
        last_diff=_format_diff(event.diff)
        if event.diff is not None
        else state.last_diff,
        last_message=event.message or event.reason or state.last_message,
        calls=event.calls if event.calls is not None else state.calls,
        cost_usd=event.cost_usd if event.cost_usd is not None else state.cost_usd,
        lines=list(state.lines),
    )


def format_event_line(event: PipelineEvent) -> str:
    parts = [f"[{event.stage}]", event.kind]
    if event.node_id:
        parts.append(event.node_id)
    if event.process:
        parts.append(event.process)
    if event.site:
        parts.append(f"@{event.site}")
    if event.status:
        parts.append(_STATUS_MARK.get(event.status, event.status))
    if event.reason:
        parts.append(f"({event.reason})")
    if event.diff is not None:
        rendered = _format_diff(event.diff)
        if rendered:
            parts.append(rendered)
    if event.message and event.kind in {
        "stage_started",
        "stage_finished",
        "verdict_ready",
    }:
        parts.append(event.message)
    return " ".join(parts)


def _node_label(event: PipelineEvent) -> str:
    bits: list[str] = [event.status or ""]
    if event.process:
        bits.append(event.process)
    if event.site:
        bits.append(event.site)
    if event.reason:
        bits.append(event.reason)
    return " ".join(item for item in bits if item)


def _format_diff(diff: StateDiff) -> str:
    chunks: list[str] = []
    if diff.protecting_groups:
        shown = ", ".join(
            f"{key}={value}" for key, value in sorted(diff.protecting_groups.items())
        )
        chunks.append(f"protecting {shown}")
    if diff.termini:
        shown = ", ".join(
            f"{key}={value}" for key, value in sorted(diff.termini.items())
        )
        chunks.append(f"termini {shown}")
    if diff.connectivity_added:
        chunks.append(f"+{len(diff.connectivity_added)} bond(s)")
    if diff.fragments:
        chunks.append("fragments " + ", ".join(diff.fragments))
    if diff.overrides:
        chunks.append(
            "overrides "
            + ", ".join(
                f"{key}={value}" for key, value in sorted(diff.overrides.items())
            )
        )
    if diff.unknowns:
        chunks.append("unknowns " + ", ".join(diff.unknowns))
    if diff.route_step:
        process = diff.route_step.get("process")
        if process:
            chunks.append(f"step {process}")
    return "; ".join(chunks)
