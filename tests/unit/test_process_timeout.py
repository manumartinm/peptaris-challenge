from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from route_agent.process_timeout import DeadlineExceeded, run_with_deadline


def _add_one(value: int) -> int:
    return value + 1


def _write_pid_and_sleep(marker: str) -> str:
    path = Path(marker)
    path.write_text(str(os.getpid()), encoding="utf-8")
    time.sleep(30)
    path.write_text("survived", encoding="utf-8")
    return "done"


class TestRunWithDeadline:
    def test_returns_function_result(self) -> None:
        assert run_with_deadline(_add_one, (3,), timeout_s=2.0) == 4

    def test_kills_hung_worker(self, tmp_path: Path) -> None:
        marker = tmp_path / "worker.txt"
        with pytest.raises(DeadlineExceeded):
            run_with_deadline(_write_pid_and_sleep, (str(marker),), timeout_s=0.3)
        deadline = time.monotonic() + 2.0
        pid = 0
        while time.monotonic() < deadline:
            if (
                marker.is_file()
                and marker.read_text(encoding="utf-8").strip().isdigit()
            ):
                pid = int(marker.read_text(encoding="utf-8").strip())
                break
            time.sleep(0.05)
        assert pid != 0
        with pytest.raises(OSError):
            os.kill(pid, 0)

    def test_unpicklable_callable_falls_back_to_fork(self) -> None:
        def nested(value: int) -> int:
            return value * 2

        assert run_with_deadline(nested, (4,), timeout_s=2.0) == 8
