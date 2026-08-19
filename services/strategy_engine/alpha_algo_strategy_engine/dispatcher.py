"""Event dispatcher: route market/order/position events to relevant instances."""

from __future__ import annotations

from uuid import UUID

from alpha_algo_contracts import MarketCandle, MarketTick
from alpha_algo_strategy_engine.instance import StrategyInstance
from alpha_algo_strategy_engine.registry import StrategyDefinition
from alpha_algo_strategy_engine.state import StrategyRunState


class StrategyDispatcher:
    """Holds running instances and routes events by enabled/instrument/timeframe."""

    def __init__(self) -> None:
        self._instances: dict[UUID, StrategyInstance] = {}
        self._definitions: dict[UUID, StrategyDefinition] = {}

    def register(self, instance: StrategyInstance, definition: StrategyDefinition) -> None:
        strategy_id = definition.identity.strategy_id
        self._instances[strategy_id] = instance
        self._definitions[strategy_id] = definition

    def unregister(self, strategy_id: UUID) -> None:
        self._instances.pop(strategy_id, None)
        self._definitions.pop(strategy_id, None)

    def instance(self, strategy_id: UUID) -> StrategyInstance | None:
        return self._instances.get(strategy_id)

    def set_enabled(self, strategy_id: UUID, enabled: bool) -> None:
        if strategy_id in self._definitions:
            from dataclasses import replace

            self._definitions[strategy_id] = replace(
                self._definitions[strategy_id], enabled=enabled
            )

    def _matches(self, strategy_id: UUID, instrument_id: UUID, timeframe=None) -> bool:
        definition = self._definitions.get(strategy_id)
        instance = self._instances.get(strategy_id)
        if definition is None or instance is None:
            return False
        if not definition.enabled:
            return False
        if instance.state != StrategyRunState.RUNNING:
            return False
        if definition.instruments and instrument_id not in definition.instruments:
            return False
        if timeframe is not None and definition.timeframes and timeframe not in definition.timeframes:
            return False
        return True

    def match_tick(self, tick: MarketTick) -> list[StrategyInstance]:
        return [
            inst
            for sid, inst in self._instances.items()
            if self._matches(sid, tick.instrument_id)
        ]

    def match_candle(self, candle: MarketCandle) -> list[StrategyInstance]:
        return [
            inst
            for sid, inst in self._instances.items()
            if self._matches(sid, candle.instrument_id, candle.timeframe)
        ]

    def match_order_update(self, update) -> list[StrategyInstance]:
        return [
            inst
            for sid, inst in self._instances.items()
            if self._matches(sid, update.instrument_id)
        ]

    def match_position_update(self, update) -> list[StrategyInstance]:
        return [
            inst
            for sid, inst in self._instances.items()
            if self._matches(sid, update.instrument_id)
        ]
