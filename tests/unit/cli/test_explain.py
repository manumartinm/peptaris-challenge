from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from route_agent.models.events import PipelineEvent, diff_state
from route_agent_cli.app import app
from route_agent_cli.explain import PlainTextObserver, format_event_line
from tests.support.validation_case import ValidationCase


class TestExplain(ValidationCase):
    runner = CliRunner()

    def test_explain_keeps_stdout_json_and_writes_progress(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ROUTE_AGENT_MOLECULAR_SKIP_3D", "true")
        request_path = tmp_path / "req.json"
        request_path.write_text(
            json.dumps(self.amide_acetylation_payload("T-EXPLAIN")),
            encoding="utf-8",
        )
        result = self.runner.invoke(
            app,
            [
                "run",
                str(request_path),
                "--no-model",
                "--explain",
                "--trace-dir",
                str(tmp_path / "traces"),
            ],
        )
        assert result.exit_code == 0, result.stdout + result.stderr
        payload = json.loads(result.stdout)
        assert payload["request_id"] == "T-EXPLAIN"
        assert "verdict" in payload
        assert "[validating]" in result.stderr or "stage_started" in result.stderr

    def test_diff_state_is_semantic_and_bounded(self) -> None:
        diff = diff_state(
            {"protected": {"K12": "pending"}, "termini": {"n": "free", "c": "acid"}},
            {
                "protected": {"K12": "Alloc"},
                "termini": {"n": "free", "c": "acid"},
                "permanent_connectivity": [{"from_atom": "K12", "bond_type": "amide"}],
            },
        )
        assert diff.protecting_groups == {"K12": "Alloc"}
        assert diff.termini == {}
        assert len(diff.connectivity_added) == 1

    def test_plain_text_observer_is_append_only(self) -> None:
        buffer = io.StringIO()
        observer = PlainTextObserver(stream=buffer)
        observer.on_event(
            PipelineEvent(
                kind="stage_started", stage="walking", message="checking routes"
            )
        )
        observer.on_event(
            PipelineEvent(
                kind="node_created",
                stage="walking",
                node_id="state_1",
                process="alloc_lipidation",
                site="K12",
                status="pass",
            )
        )
        observer.close()
        lines = buffer.getvalue().splitlines()
        assert any("walking" in line for line in lines)
        assert format_event_line(
            PipelineEvent(
                kind="branch_pruned", stage="walking", node_id="state_2", status="fail"
            )
        ).startswith("[walking]")
