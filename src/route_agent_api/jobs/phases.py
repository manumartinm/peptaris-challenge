"""Translate pipeline events into Trace Explorer job phases."""

from __future__ import annotations

from route_agent.models.events import PipelineEvent
from route_agent_api.models import JOB_PHASES, JobPhase, JobProgress, JobState

_STAGE_TO_PHASE: dict[str, JobPhase] = {
    "validating": "validate",
    "walking": "walk",
    "post_graph": "molecular",
    "judging": "judge",
    "assembling": "assemble",
    "writing": "assemble",
}


def apply_event_to_state(state: JobState, event: PipelineEvent) -> JobState:
    if state.status == "queued":
        state.status = "running"
    phase = phase_for_event(event)
    if phase is not None:
        complete_prior_phases(state, phase)
        state.phase = phase
    if event.kind == "stage_finished" and event.stage == "validating":
        mark_complete(state, "validate")
    elif event.kind == "winner_selected":
        mark_complete(state, "molecular")
        mark_complete(state, "intent")
    elif event.kind == "judge_finished":
        mark_complete(state, "judge")
    elif event.kind == "verdict_ready":
        mark_complete(state, "assemble")
    if event.current is not None or event.total is not None:
        state.progress = JobProgress(
            current=event.current,
            total=event.total,
            label=activity_label(event),
        )
    activity = activity_label(event)
    if activity:
        state.activity = activity
    return state


def phase_for_event(event: PipelineEvent) -> JobPhase | None:
    if event.kind == "molecular_validated":
        return "molecular"
    if event.kind == "intent_checked":
        return "intent"
    if event.kind in {
        "stage_started",
        "stage_finished",
        "verdict_ready",
        "judge_finished",
    }:
        return _STAGE_TO_PHASE.get(event.stage)
    return None


def complete_prior_phases(state: JobState, phase: JobPhase) -> None:
    index = JOB_PHASES.index(phase)
    for prior in JOB_PHASES[:index]:
        mark_complete(state, prior)


def mark_complete(state: JobState, phase: JobPhase) -> None:
    if phase not in state.completed_phases:
        state.completed_phases.append(phase)


def activity_label(event: PipelineEvent) -> str | None:
    bits = [item for item in (event.process, event.site, event.node_id) if item]
    if bits:
        return " · ".join(bits)
    return event.message
