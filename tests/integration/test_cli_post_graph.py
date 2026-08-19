from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.support.cli import CliCase


class TestCliPostGraph(CliCase):
    def test_post_graph_writes_internal_report(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ROUTE_AGENT_MOLECULAR_SKIP_3D", "true")
        path = self.write_json(tmp_path, self.amide_acetylation_payload("T-PG-CLI"))
        output = tmp_path / "out.json"
        result = self.invoke(
            "post-graph", str(path), "--no-model", "--output", str(output)
        )
        assert result.exit_code == 0, result.stdout + result.stderr
        payload = json.loads(output.read_text(encoding="utf-8"))
        assert payload["request_id"] == "T-PG-CLI"
        assert payload["selected_id"]
        assert "verdict" not in payload
        winner = next(
            item
            for item in payload["candidates"]
            if item["node_id"] == payload["selected_id"]
        )
        assert winner["molecular"]["two_d"]["valid"] is True
