"""Run a callable in a child process and kill it when the deadline expires."""

from __future__ import annotations

import multiprocessing
import pickle
import sys
import warnings
from collections.abc import Callable
from contextlib import suppress
from typing import Any


class DeadlineExceeded(TimeoutError):
    def __init__(self, timeout_s: float) -> None:
        super().__init__(f"deadline exceeded after {timeout_s}s")
        self.timeout_s = timeout_s


class WorkerStartError(RuntimeError):
    """The child process could not be launched (usually an unpicklable callable)."""


def _call_and_send(conn: Any, func: Callable[..., Any], args: tuple[Any, ...]) -> None:
    try:
        conn.send(("ok", func(*args)))
    except BaseException as exc:
        with suppress(Exception):
            conn.send(("err", f"{type(exc).__name__}:{exc}"))
    finally:
        conn.close()


def _kill_process(proc: Any) -> None:
    if not proc.is_alive():
        proc.join(0)
        return
    proc.terminate()
    proc.join(1)
    if proc.is_alive():
        proc.kill()
        proc.join(1)


def _context_names() -> tuple[str, ...]:
    if sys.platform == "win32":
        return ("spawn",)
    return ("spawn", "fork")


def run_with_deadline[T](
    func: Callable[..., T],
    args: tuple[Any, ...] = (),
    *,
    timeout_s: float,
) -> T:
    last_error: Exception | None = None
    names = _context_names()
    for index, name in enumerate(names):
        try:
            return _run_in_context(name, func, args, timeout_s)
        except DeadlineExceeded:
            raise
        except WorkerStartError as exc:
            last_error = exc
            if index == len(names) - 1:
                raise
            continue
    raise RuntimeError(f"could not start deadline worker: {last_error}")


def _run_in_context[T](
    name: str,
    func: Callable[..., T],
    args: tuple[Any, ...],
    timeout_s: float,
) -> T:
    ctx: Any = multiprocessing.get_context(name)
    parent, child = ctx.Pipe(duplex=False)
    proc = ctx.Process(
        target=_call_and_send,
        args=(child, func, args),
        name="route-agent-deadline",
    )
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=".*use of fork\\(\\).*",
            category=DeprecationWarning,
        )
        try:
            proc.start()
        except (pickle.PicklingError, AttributeError, TypeError) as exc:
            child.close()
            parent.close()
            raise WorkerStartError(str(exc)) from exc
    child.close()
    try:
        if parent.poll(timeout_s):
            status, payload = parent.recv()
            proc.join(5)
            if status == "ok":
                return payload  # type: ignore[no-any-return]
            raise RuntimeError(str(payload))
        _kill_process(proc)
        raise DeadlineExceeded(timeout_s)
    finally:
        parent.close()
        if proc.is_alive():
            _kill_process(proc)
