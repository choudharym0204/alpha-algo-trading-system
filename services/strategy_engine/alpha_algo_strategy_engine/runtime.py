"""Strategy runtime orchestrator: registry + instances + dispatch + signals.

This is the Phase 4 composition root. It consumes Phase-3 market events through
the `MarketDataEngine` consumer abstraction (never provider internals), runs each
strategy instance with isolation (submit-all-then-collect so a slow strategy does
not block unrelated instances), validates/deduplicates signals, and fans accepted
signals out to downstream consumers (Phase 5 will own the dedicated
signal-processing layer).

LIVE trading mode is blocked (fail-closed); only BACKTEST and PAPER are allowed.
"""

from __future__ import annotations

import concurrent.futures
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Callable
from uuid import UUID

from alpha_algo_contracts import MarketCandle, MarketTick, StrategySignal
from alpha_algo_strategy_engine.dispatcher import StrategyDispatcher
from alpha_algo_strategy_engine.errors import (
    StrategyNotFoundError,
    TradingModeError,
)
from alpha_algo_strategy_engine.instance import StrategyInstance
from alpha_algo_strategy_engine.metrics import StrategyMetrics
from alpha_algo_strategy_engine.registry import StrategyDefinition, StrategyRegistry
from alpha_algo_strategy_engine.run_record import StrategyRunRecord
from alpha_algo_strategy_engine.state import StrategyRunState, TradingMode
from alpha_algo_strategies import OrderUpdate, PositionUpdate

logger = logging.getLogger(__name__)

SignalConsumer = Callable[[StrategySignal], None]
_ALLOWED_MODES = frozenset({TradingMode.BACKTEST, TradingMode.PAPER})


class StrategyRuntime:
    def __init__(
        self,
        *,
        registry: StrategyRegistry | None = None,
        dispatcher: StrategyDispatcher | None = None,
        metrics: StrategyMetrics | None = None,
        clock: Callable[[], datetime] | None = None,
        callback_timeout_seconds: float | None = 30.0,
        max_workers: int = 8,
    ) -> None:
        self._registry = registry or StrategyRegistry()
        self._dispatcher = dispatcher or StrategyDispatcher()
        self._metrics = metrics or StrategyMetrics()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._callback_timeout = callback_timeout_seconds
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._runs: dict[UUID, StrategyRunRecord] = {}
        self._signal_consumers: list[SignalConsumer] = []

    @property
    def registry(self) -> StrategyRegistry:
        return self._registry

    @property
    def metrics(self) -> StrategyMetrics:
        return self._metrics

    def register(self, definition: StrategyDefinition) -> None:
        self._registry.register(definition)

    def unregister(self, strategy_id: UUID) -> None:
        self._registry.unregister(strategy_id)
        self._dispatcher.unregister(strategy_id)
        self._runs.pop(strategy_id, None)

    def add_signal_consumer(self, consumer: SignalConsumer) -> None:
        self._signal_consumers.append(consumer)

    # -- lifecycle -----------------------------------------------------------
    def start(
        self,
        strategy_id: UUID,
        trading_mode: TradingMode | str,
        *,
        config_values: dict[str, object] | None = None,
    ) -> UUID:
        mode = trading_mode if isinstance(trading_mode, TradingMode) else TradingMode(trading_mode)
        if mode not in _ALLOWED_MODES:
            raise TradingModeError(f"trading mode not allowed: {mode.value}")

        definition = self._registry.get(strategy_id)
        strategy_impl = definition.factory()
        instance = StrategyInstance(
            definition,
            strategy_impl,
            config_values=config_values,
            clock=self._clock,
            metrics=self._metrics,
        )
        instance.initialize()
        instance.start()

        self._dispatcher.register(instance, definition)
        record = StrategyRunRecord(
            strategy_id=strategy_id,
            version=definition.identity.version,
            config_hash=definition.identity.config_hash,
            code_hash=definition.identity.code_hash,
            trading_mode=mode,
            started_at=self._clock(),
            state=instance.state,
        )
        self._runs[strategy_id] = record
        return record.run_id

    def stop(self, strategy_id: UUID) -> None:
        instance = self._require_instance(strategy_id)
        instance.stop()
        self._dispatcher.set_enabled(strategy_id, False)
        record = self._runs.get(strategy_id)
        if record is not None:
            record.state = instance.state
            record.stopped_at = self._clock()

    def pause(self, strategy_id: UUID) -> None:
        self._require_instance(strategy_id).pause()

    def resume(self, strategy_id: UUID) -> None:
        self._require_instance(strategy_id).resume()

    def _require_instance(self, strategy_id: UUID) -> StrategyInstance:
        instance = self._dispatcher.instance(strategy_id)
        if instance is None:
            raise StrategyNotFoundError(f"strategy not running: {strategy_id}")
        return instance

    def run_record(self, strategy_id: UUID) -> StrategyRunRecord | None:
        return self._runs.get(strategy_id)

    def status(self, strategy_id: UUID) -> dict[str, object]:
        record = self._runs.get(strategy_id)
        instance = self._dispatcher.instance(strategy_id)
        return {
            "strategy_id": str(strategy_id),
            "state": instance.state.value if instance else "not_started",
            "run_id": str(record.run_id) if record else None,
            "trading_mode": record.trading_mode.value if record else None,
            "reason": record.reason if record else None,
        }

    # -- event entry points (Phase 3 boundary) ------------------------------
    def on_tick(self, tick: MarketTick) -> list[StrategySignal]:
        instances = self._dispatcher.match_tick(tick)
        return self._dispatch(instances, lambda inst: inst.on_tick(tick), tick.timestamp)

    def on_candle(self, candle: MarketCandle) -> list[StrategySignal]:
        instances = self._dispatcher.match_candle(candle)
        return self._dispatch(instances, lambda inst: inst.on_candle(candle), candle.candle_start)

    def on_order_update(self, update: OrderUpdate) -> list[StrategySignal]:
        instances = self._dispatcher.match_order_update(update)
        return self._dispatch(instances, lambda inst: inst.on_order_update(update), update.timestamp)

    def on_position_update(self, update: PositionUpdate) -> list[StrategySignal]:
        instances = self._dispatcher.match_position_update(update)
        return self._dispatch(
            instances, lambda inst: inst.on_position_update(update), update.timestamp
        )

    def _dispatch(
        self,
        instances: list[StrategyInstance],
        run_fn: Callable[[StrategyInstance], list[StrategySignal]],
        event_timestamp: datetime,
    ) -> list[StrategySignal]:
        for _ in instances:
            self._metrics.inc("events_dispatched")

        accepted: list[StrategySignal] = []
        if not instances:
            return accepted

        lag = (self._clock() - event_timestamp).total_seconds()
        if lag > 0:
            self._metrics.record_event_lag(lag)

        # Submit all instances first so a slow strategy occupies its own worker
        # and never blocks unrelated instances. Collect with as_completed so an
        # already-finished instance's signals fan out without waiting on a slow
        # neighbour's full timeout.
        futures = {self._executor.submit(run_fn, inst): inst for inst in instances}
        try:
            for future in concurrent.futures.as_completed(futures, timeout=self._callback_timeout):
                inst = futures[future]
                try:
                    signals = future.result()
                except Exception as exc:  # noqa: BLE001 - isolate unexpected fault
                    inst.mark_failed(str(exc))
                    self._metrics.inc("events_dropped")
                    self._record_failure(inst)
                    logger.warning("strategy %s failed: %s", inst.identity.code, exc)
                    continue
                self._collect(inst, signals, event_timestamp, accepted)
                if inst.state == StrategyRunState.FAILED:
                    self._record_failure(inst)
        except concurrent.futures.TimeoutError:
            pass  # remaining futures handled below

        # Anything still pending hit the timeout: cancel (best effort) + isolate.
        for future, inst in futures.items():
            if not future.done():
                future.cancel()
                inst.mark_failed("callback_timeout")
                self._metrics.inc("events_dropped")
                self._record_failure(inst)
                logger.warning("strategy %s timed out", inst.identity.code)

        return accepted

    def _record_failure(self, instance: StrategyInstance) -> None:
        record = self._runs.get(instance.identity.strategy_id)
        if record is not None:
            record.reason = instance.fail_reason
            record.state = instance.state
            record.stopped_at = self._clock()

    def _collect(
        self,
        instance: StrategyInstance,
        signals: list[StrategySignal],
        event_timestamp: datetime,
        accepted: list[StrategySignal],
    ) -> None:
        for signal in signals:
            enriched = self._enrich(signal, instance, event_timestamp)
            accepted.append(enriched)
            self._fan_out(enriched)

    def _enrich(
        self, signal: StrategySignal, instance: StrategyInstance, event_timestamp: datetime
    ) -> StrategySignal:
        """Attach code hash + run id + event timestamp for full traceability.

        Direct assignment (not setdefault) so a strategy cannot spoof these
        authoritative fields by pre-populating them in its own metadata.
        """
        record = self._runs.get(instance.identity.strategy_id)
        metadata = dict(signal.metadata)
        metadata["strategy_code_hash"] = instance.identity.code_hash
        metadata["strategy_run_id"] = str(record.run_id) if record else None
        metadata["event_timestamp"] = event_timestamp.isoformat()
        return signal.model_copy(update={"metadata": metadata})

    def _fan_out(self, signal: StrategySignal) -> None:
        for consumer in self._signal_consumers:
            try:
                consumer(signal)
            except Exception as exc:  # noqa: BLE001 - isolate consumer faults
                logger.warning("signal consumer failed: %s", exc)

    def shutdown(self) -> None:
        for strategy_id in list(self._runs):
            try:
                self.stop(strategy_id)
            except Exception:  # noqa: BLE001 - best-effort shutdown
                logger.debug("shutdown stop failed for %s", strategy_id, exc_info=True)
        # Do not wait on hung callbacks; cancel pending futures so shutdown never
        # blocks indefinitely behind a timed-out strategy.
        self._executor.shutdown(wait=False, cancel_futures=True)
