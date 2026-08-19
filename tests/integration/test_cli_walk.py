from __future__ import annotations

import json
from pathlib import Path

from tests.support.cli import CliCase


class TestCliWalk(CliCase):
    def test_walk_req01_writes_tree_without_verdict(self, tmp_path: Path) -> None:
        request_path = self.write_json(
            tmp_path, self.design_request_row("REQ-01"), "req01.json"
        )
        output = tmp_path / "out.json"

        result = self.invoke(
            "walk", str(request_path), "--no-model", "--output", str(output)
        )

        assert result.exit_code == 0, result.stdout + result.stderr
        payload = json.loads(output.read_text(encoding="utf-8"))
        assert payload["request_id"] == "REQ-01"
        assert "verdict" not in payload
        nodes = {node["id"]: node for node in payload["nodes"]}
        root_id = payload["root_id"]
        assert root_id in nodes
        children = nodes[root_id]["children"]
        assert payload["surviving_ids"] == children
        assert children
        processes = [
            nodes[node_id]["candidate"]["process"]
            for node_id in children
            if nodes[node_id]["candidate"] is not None
        ]
        assert processes
        assert all("lipidation" in process for process in processes)
        for node_id in children:
            assert nodes[node_id]["state"]["status"] in {"pass", "fail", "degraded"}
            assert nodes[node_id]["agent_result"]["passed"] is None
        assert "sk-" not in result.stdout
        assert "sk-" not in result.stderr
