"""Shared CLI invocation helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from click.testing import CliRunner, Result

from route_agent.models.verdict import RouteVerdict
from route_agent_cli.app import app
from tests.support.validation_case import ValidationCase

PUBLIC_VERDICT_FIELDS = frozenset(RouteVerdict.model_fields)
VERDICTS = {
    "feasible",
    "feasible_with_changes",
    "infeasible",
    "insufficient_information",
}


def invoke_cli(*args: str) -> Result:
    return CliRunner().invoke(app, list(args))


def write_json(tmp_path: Path, payload: object, name: str = "req.json") -> Path:
    path = tmp_path / name
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class CliCase(ValidationCase):
    runner = CliRunner()

    def write_json(
        self, tmp_path: Path, payload: object, name: str = "req.json"
    ) -> Path:
        return write_json(tmp_path, payload, name)

    def invoke(self, *args: str) -> Result:
        return self.runner.invoke(app, list(args))
