"""Shared helpers for Phase 4 strategy-runtime tests (not a test module)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from alpha_algo_contracts import (
    CandleTimeframe,
    MarketCandle,
    MarketTick,
    SignalAction,
    StrategySignal,
)
from alpha_algo_strategy_engine import (
    StrategyDefinition,
    StrategyIdentity,
    compute_code_hash,
    compute_config_hash,
)
from alpha_algo_strategies import (
    OrderUpdate,
    PositionUpdate,
    StrategyContext,
    StrategyLifecycle,
)


def make_identity(
    *,
    strategy_id: UUID | None = None,
    code: str = "sma",
    name: str = "SMA",
    version: str = "1.0.0",
    config: dict | None = None,
) -> StrategyIdentity:
    return StrategyIdentity(
        strategy_id=strategy_id or uuid4(),
        code=code,
        name=name,
        version=version,
        config_hash=compute_config_hash(config or {}),
        code_hash=compute_code_hash(code),
        created_at=datetime.now(UTC),
    )


def make_definition(
    *,
    identity=None,
    factory=None,
    enabled: bool = True,
    instruments=frozenset(),
    timeframes=frozenset(),
    config=None,
) -> StrategyDefinition:
    identity = identity or make_identity(config=config or {})
    factory = factory or RecordingStrategy
    return StrategyDefinition(
        identity=identity,
        factory=factory,
        enabled=enabled,
        instruments=frozenset(instruments),
        timeframes=frozenset(timeframes),
        config=dict(config or {}),
    )


def make_tick(*, instrument_id: UUID | None = None, timestamp: datetime | None = None) -> MarketTick:
    ts = timestamp or datetime.now(UTC)
    return MarketTick(
        instrument_id=instrument_id or uuid4(),
        exchange="NSE",
        symbol="RELIANCE",
        timestamp=ts,
        ltp=Decimal("2450.25"),
        source_broker="fake",
        source_sequence="seq-1",
        received_at=ts,
    )


def make_candle(
    *,
    instrument_id: UUID | None = None,
    candle_start: datetime | None = None,
    timeframe: CandleTimeframe = CandleTimeframe.ONE_MINUTE,
    close: str = "105",
) -> MarketCandle:
    ts = candle_start or datetime.now(UTC)
    return MarketCandle(
        instrument_id=instrument_id or uuid4(),
        exchange="NSE",
        symbol="RELIANCE",
        timeframe=timeframe,
        candle_start=ts,
        open_price=Decimal("100"),
        high_price=Decimal("110"),
        low_price=Decimal("95"),
        close_price=Decimal(close),
        source_broker="fake",
        generated_at=ts,
    )


def make_signal(
    *,
    strategy_id: UUID,
    version: str = "1.0.0",
    config_hash: str,
    instrument_id: UUID | None = None,
    action: SignalAction = SignalAction.BUY,
    timestamp: datetime | None = None,
    confidence: Decimal = Decimal("0.8"),
    reason: str = "test signal",
) -> StrategySignal:
    return StrategySignal(
        strategy_id=strategy_id,
        strategy_version=version,
        strategy_config_hash=config_hash,
        instrument_id=instrument_id or uuid4(),
        action=action,
        timestamp=timestamp or datetime.now(UTC),
        confidence=confidence,
        reason=reason,
    )


class RecordingStrategy(StrategyLifecycle):
    """Test double that records lifecycle calls and can emit signals or raise."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.raise_on: str | None = None
        self.signals_to_emit: list[StrategySignal] = []

    def initialize(self, context: StrategyContext) -> None:
        self.calls.append("initialize")

    def on_start(self, context: StrategyContext) -> None:
        self.calls.append("on_start")
        self._maybe_raise("on_start")

    def on_stop(self, context: StrategyContext) -> None:
        self.calls.append("on_stop")
        self._maybe_raise("on_stop")

    def on_tick(self, context: StrategyContext, tick) -> None:
        self.calls.append("on_tick")
        self._maybe_raise("on_tick")
        for sig in self.signals_to_emit:
            context.emit_signal(sig)

    def on_candle(self, context: StrategyContext, candle) -> None:
        self.calls.append("on_candle")
        self._maybe_raise("on_candle")
        for sig in self.signals_to_emit:
            context.emit_signal(sig)

    def on_order_update(self, context: StrategyContext, update: OrderUpdate) -> None:
        self.calls.append("on_order_update")
        self._maybe_raise("on_order_update")

    def on_position_update(self, context: StrategyContext, update: PositionUpdate) -> None:
        self.calls.append("on_position_update")
        self._maybe_raise("on_position_update")

    def _maybe_raise(self, hook: str) -> None:
        if self.raise_on == hook:
            raise RuntimeError(f"boom in {hook}")
