"""Conflict-tree walker and ledger. Import public names from this package."""

from __future__ import annotations

from route_agent.conflict.handles import resolve_pending_handles
from route_agent.conflict.ledger import Ledger
from route_agent.conflict.walker import ConflictWalker, StageOutcome

_resolve_pending_handles = resolve_pending_handles

__all__ = [
    "ConflictWalker",
    "Ledger",
    "StageOutcome",
    "_resolve_pending_handles",
    "resolve_pending_handles",
]
