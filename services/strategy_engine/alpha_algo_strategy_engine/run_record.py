"""Strategy run record — identifies one runtime instance of a strategy version."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from alpha_algo_strategy_engine.state import StrategyRunState, TradingMode


@dataclass
class StrategyRunRecord:
    strategy_id: UUID
    version: str
    config_hash: str
    code_hash: str | None
    trading_mode: TradingMode
    run_id: UUID = field(default_factory=uuid4)
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    state: StrategyRunState = StrategyRunState.CREATED
    reason: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "run_id": str(self.run_id),
            "strategy_id": str(self.strategy_id),
            "version": self.version,
            "config_hash": self.config_hash,
            "code_hash": self.code_hash,
            "trading_mode": self.trading_mode.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "stopped_at": self.stopped_at.isoformat() if self.stopped_at else None,
            "state": self.state.value,
            "reason": self.reason,
        }
