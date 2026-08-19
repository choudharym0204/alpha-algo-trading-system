from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Mapping, Protocol, runtime_checkable
from uuid import UUID

from alpha_algo_contracts import MarketCandle, MarketTick, StrategySignal


def _require_timezone(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True)
class OrderUpdate:
    order_id: UUID
    instrument_id: UUID
    status: str
    timestamp: datetime
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_timezone(self.timestamp, "timestamp")
        if not self.status.strip():
            raise ValueError("status is required")


@dataclass(frozen=True)
class PositionUpdate:
    position_id: UUID
    instrument_id: UUID
    quantity: Decimal
    timestamp: datetime
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_timezone(self.timestamp, "timestamp")


@dataclass
class StrategyContext:
    strategy_id: UUID
    strategy_version: str
    strategy_config_hash: str
    config: Mapping[str, object] = field(default_factory=dict)
    state: dict[str, object] = field(default_factory=dict)
    emitted_signals: list[StrategySignal] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.strategy_version.strip():
            raise ValueError("strategy_version is required")
        if not self.strategy_config_hash.strip():
            raise ValueError("strategy_config_hash is required")

    def emit_signal(self, signal: StrategySignal) -> None:
        if signal.strategy_id != self.strategy_id:
            raise ValueError("signal strategy_id does not match context")
        if signal.strategy_version != self.strategy_version:
            raise ValueError("signal strategy_version does not match context")
        if signal.strategy_config_hash != self.strategy_config_hash:
            raise ValueError("signal strategy_config_hash does not match context")
        self.emitted_signals.append(signal)


@runtime_checkable
class StrategyLifecycle(Protocol):
    def initialize(self, context: StrategyContext) -> None:
        ...

    def on_start(self, context: StrategyContext) -> None:
        ...

    def on_tick(self, context: StrategyContext, tick: MarketTick) -> None:
        ...

    def on_candle(self, context: StrategyContext, candle: MarketCandle) -> None:
        ...

    def on_order_update(self, context: StrategyContext, update: OrderUpdate) -> None:
        ...

    def on_position_update(self, context: StrategyContext, update: PositionUpdate) -> None:
        ...

    def on_stop(self, context: StrategyContext) -> None:
        ...
