from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

from tests.support.validation_case import REPO_ROOT

SCORE_PY = REPO_ROOT / "data" / "score.py"
SCHEMA_JSON = REPO_ROOT / "data" / "schema.json"


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    return path


def write_eval_pair(
    directory: Path,
    requests: list[dict[str, Any]],
    expected: list[dict[str, Any]],
) -> tuple[Path, Path]:
    return (
        write_jsonl(directory / "requests.jsonl", requests),
        write_jsonl(directory / "expected.jsonl", expected),
    )


def validate_jsonl(path: Path) -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, str(SCORE_PY), "--validate", str(path), str(SCHEMA_JSON)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode in {0, 1}, completed.stderr
    return cast(dict[str, Any], json.loads(completed.stdout))


def validate_schema(payload: dict[str, Any], tmp_path: Path) -> dict[str, Any]:
    return validate_jsonl(write_jsonl(tmp_path / "actual.jsonl", [payload]))


def score_outputs(expected_path: Path, actual_path: Path) -> tuple[dict[str, Any], str]:
    completed = subprocess.run(
        [sys.executable, str(SCORE_PY), str(expected_path), str(actual_path), "--json"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    return cast(dict[str, Any], json.loads(completed.stdout)), completed.stdout
