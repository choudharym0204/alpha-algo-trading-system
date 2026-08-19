"""Strategy directory abstraction — decouples the signal engine from the
Phase-4 registry so ingestion can validate "known / enabled / version / hash /
instrument subscription" without importing strategy-engine internals.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class StrategyRecord:
    strategy_id: UUID
    version: str
    config_hash: str
    code_hash: str | None
    enabled: bool
    # None means "all instruments"; an empty/filled frozenset restricts routing.
    instruments: frozenset[UUID] | None = None


class StrategyDirectory(Protocol):
    def lookup(self, strategy_id: UUID) -> StrategyRecord | None:
        """Return the registered record for a strategy, or None if unknown."""
        ...
