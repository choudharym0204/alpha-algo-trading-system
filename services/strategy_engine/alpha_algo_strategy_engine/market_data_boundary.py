"""Phase 3 → Phase 4 boundary.

Consumes the Phase-3 `MarketDataEngine` through its consumer abstraction
(`add_tick_consumer` / `add_candle_consumer`) and forwards normalized events to
the strategy runtime. No provider internals are imported — the architecture is
Provider → MarketDataAdapter → MarketDataService → StrategyRuntime, never
Strategy → Provider SDK.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from alpha_algo_market_data import MarketDataEngine
    from alpha_algo_strategy_engine.runtime import StrategyRuntime


def connect_market_data(engine: "MarketDataEngine", runtime: "StrategyRuntime") -> "MarketDataEngine":
    """Wire a Phase-3 engine to a Phase-4 runtime and return the engine."""
    engine.add_tick_consumer(runtime.on_tick)
    engine.add_candle_consumer(runtime.on_candle)
    return engine
