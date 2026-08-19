"""Reference strategies demonstrating indicator integration + signal emission."""

from __future__ import annotations

from decimal import Decimal

from alpha_algo_contracts import MarketCandle, SignalAction, StrategySignal
from alpha_algo_indicators import simple_moving_average
from alpha_algo_strategies import (
    OrderUpdate,
    PositionUpdate,
    StrategyContext,
    StrategyLifecycle,
)

_CLOSES_KEY = "closes"


class SmaCrossStrategy(StrategyLifecycle):
    """Emits BUY/SELL on a fast/SMA crossover using `simple_moving_average`.

    Demonstrates the contract without any broker/network/DB access: it reads its
    config (fast_period / slow_period), keeps a rolling close-price window in
    `context.state`, and emits identity-consistent signals via `emit_signal`.
    """

    def initialize(self, context: StrategyContext) -> None:
        context.state[_CLOSES_KEY] = []

    def on_start(self, context: StrategyContext) -> None:
        return None

    def on_stop(self, context: StrategyContext) -> None:
        return None

    def on_tick(self, context: StrategyContext, tick) -> None:
        return None

    def on_order_update(self, context: StrategyContext, update: OrderUpdate) -> None:
        return None

    def on_position_update(self, context: StrategyContext, update: PositionUpdate) -> None:
        return None

    def on_candle(self, context: StrategyContext, candle: MarketCandle) -> None:
        fast = int(context.config.get("fast_period", 5))
        slow = int(context.config.get("slow_period", 20))
        closes = context.state.setdefault(_CLOSES_KEY, [])
        closes.append(candle.close_price)
        if len(closes) < slow + 1:
            return

        fast_now = simple_moving_average(closes, period=fast)[-1]
        slow_now = simple_moving_average(closes, period=slow)[-1]
        fast_prev = simple_moving_average(closes[:-1], period=fast)[-1]
        slow_prev = simple_moving_average(closes[:-1], period=slow)[-1]

        action = SignalAction.HOLD
        if fast_now is not None and slow_now is not None:
            if fast_now > slow_now and (fast_prev is None or slow_prev is None or fast_prev <= slow_prev):
                action = SignalAction.BUY
            elif fast_now < slow_now and (fast_prev is None or slow_prev is None or fast_prev >= slow_prev):
                action = SignalAction.SELL

        context.emit_signal(
            StrategySignal(
                strategy_id=context.strategy_id,
                strategy_version=context.strategy_version,
                strategy_config_hash=context.strategy_config_hash,
                instrument_id=candle.instrument_id,
                action=action,
                timestamp=candle.candle_start,
                confidence=Decimal("0.8"),
                reason=f"SMA {fast}/{slow} crossover",
            )
        )
