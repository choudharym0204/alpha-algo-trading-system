"""Strategy instance: lifecycle enforcement + exception isolation + signal
validation/dedup on top of the existing `StrategyLifecycle`/`StrategyContext`
contracts."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from threading import Lock
from time import perf_counter
from typing import Callable
from uuid import UUID

from alpha_algo_contracts import MarketCandle, MarketTick, StrategySignal
from alpha_algo_strategy_engine.config import StrategyConfig
from alpha_algo_strategy_engine.duplicate import SignalDeduplicator
from alpha_algo_strategy_engine.errors import ConfigValidationError, LifecycleError
from alpha_algo_strategy_engine.identity import StrategyIdentity, compute_config_hash
from alpha_algo_strategy_engine.metrics import StrategyMetrics
from alpha_algo_strategy_engine.registry import StrategyDefinition
from alpha_algo_strategy_engine.signal_validation import SignalValidator
from alpha_algo_strategy_engine.state import RunStateMachine, StrategyRunState
from alpha_algo_strategies import (
    OrderUpdate,
    PositionUpdate,
    StrategyContext,
    StrategyLifecycle,
)

logger = logging.getLogger(__name__)

# Signals are expected to be emitted with a timestamp close to the triggering
# event time (Phase-3 staleness semantics); a small tolerance covers skew.
_DEFAULT_SIGNAL_MAX_AGE = timedelta(seconds=5)


class StrategyInstance:
    """Wraps one strategy implementation with controlled lifecycle + isolation.

    A per-instance lock serializes callbacks so a single instance is never
    executed concurrently by multiple producers (its `context.state` and
    `emitted_signals` are not concurrency-safe by contract).
    """

    def __init__(
        self,
        definition: StrategyDefinition,
        strategy_impl: StrategyLifecycle,
        *,
        config_values: dict[str, object] | None = None,
        clock: Callable[[], datetime] | None = None,
        signal_validator: SignalValidator | None = None,
        deduplicator: SignalDeduplicator | None = None,
        metrics: StrategyMetrics | None = None,
    ) -> None:
        self._definition = definition
        self._identity = definition.identity
        self._strategy = strategy_impl
        self._state = RunStateMachine(StrategyRunState.CREATED)
        self._initialized = False
        self._fail_reason: str | None = None
        self._metrics = metrics or StrategyMetrics()
        self._validator = signal_validator or SignalValidator(
            clock=clock, max_age=_DEFAULT_SIGNAL_MAX_AGE
        )
        self._deduplicator = deduplicator or SignalDeduplicator()
        self._lock = Lock()

        config_values = config_values if config_values is not None else dict(definition.config)
        actual_hash = compute_config_hash(config_values)
        if actual_hash != self._identity.config_hash:
            raise ConfigValidationError(
                f"config hash mismatch: {actual_hash} != {self._identity.config_hash}"
            )
        config = StrategyConfig(values=config_values, config_hash=self._identity.config_hash)
        self._context = StrategyContext(
            strategy_id=self._identity.strategy_id,
            strategy_version=self._identity.version,
            strategy_config_hash=self._identity.config_hash,
            config=dict(config.values),
        )
        self._allowed_instruments = (
            set(definition.instruments) if definition.instruments else None
        )

    # -- read-only accessors -------------------------------------------------
    @property
    def state(self) -> StrategyRunState:
        return self._state.state

    @property
    def identity(self) -> StrategyIdentity:
        return self._identity

    @property
    def context(self) -> StrategyContext:
        return self._context

    @property
    def metrics(self) -> StrategyMetrics:
        return self._metrics

    @property
    def fail_reason(self) -> str | None:
        return self._fail_reason

    # -- lifecycle -----------------------------------------------------------
    def initialize(self) -> None:
        if self._initialized:
            raise LifecycleError("strategy already initialized")
        if self._state.state != StrategyRunState.CREATED:
            raise LifecycleError("initialize only allowed from CREATED")
        self._state.transition(StrategyRunState.INITIALIZING)
        try:
            self._strategy.initialize(self._context)
        except Exception as exc:  # noqa: BLE001 - isolate strategy fault
            self._fail(str(exc))
            raise LifecycleError(f"initialize failed: {exc}") from exc
        self._state.transition(StrategyRunState.CREATED)
        self._initialized = True

    def start(self) -> None:
        if not self._initialized:
            raise LifecycleError("must initialize before start")
        if self._state.state != StrategyRunState.CREATED:
            raise LifecycleError("start only allowed once from CREATED")
        self._state.transition(StrategyRunState.RUNNING)
        try:
            self._strategy.on_start(self._context)
        except Exception as exc:  # noqa: BLE001
            self._fail(str(exc))
            raise LifecycleError(f"on_start failed: {exc}") from exc
        self._metrics.inc("strategies_started")

    def pause(self) -> None:
        if self._state.state != StrategyRunState.RUNNING:
            raise LifecycleError("pause only allowed from RUNNING")
        self._state.transition(StrategyRunState.PAUSED)
        self._metrics.inc("strategies_paused")

    def resume(self) -> None:
        if self._state.state != StrategyRunState.PAUSED:
            raise LifecycleError("resume only allowed from PAUSED")
        self._state.transition(StrategyRunState.RUNNING)
        self._metrics.inc("strategies_resumed")

    def stop(self) -> None:
        if self._state.state not in (StrategyRunState.RUNNING, StrategyRunState.PAUSED):
            raise LifecycleError("stop only allowed from RUNNING/PAUSED")
        self._state.transition(StrategyRunState.STOPPING)
        try:
            self._strategy.on_stop(self._context)
        except Exception as exc:  # noqa: BLE001
            self._fail(str(exc))
            raise LifecycleError(f"on_stop failed: {exc}") from exc
        self._state.transition(StrategyRunState.STOPPED)
        self._metrics.inc("strategies_stopped")

    def mark_failed(self, reason: str) -> None:
        """Force the instance into FAILED (e.g. callback timeout at the runtime)."""
        self._fail(reason)

    # -- event callbacks (return accepted signals) --------------------------
    def on_tick(self, tick: MarketTick) -> list[StrategySignal]:
        return self._dispatch(self._strategy.on_tick, tick, tick.timestamp)

    def on_candle(self, candle: MarketCandle) -> list[StrategySignal]:
        return self._dispatch(self._strategy.on_candle, candle, candle.candle_start)

    def on_order_update(self, update: OrderUpdate) -> list[StrategySignal]:
        return self._dispatch(self._strategy.on_order_update, update, update.timestamp)

    def on_position_update(self, update: PositionUpdate) -> list[StrategySignal]:
        return self._dispatch(self._strategy.on_position_update, update, update.timestamp)

    # -- internals -----------------------------------------------------------
    def _require_running(self) -> None:
        if self._state.state != StrategyRunState.RUNNING:
            raise LifecycleError(
                f"callback not allowed in state {self._state.state.value}"
            )

    def _dispatch(self, callback: Callable, event, event_timestamp: datetime) -> list[StrategySignal]:
        with self._lock:
            return self._dispatch_locked(callback, event, event_timestamp)

    def _dispatch_locked(
        self, callback: Callable, event, event_timestamp: datetime
    ) -> list[StrategySignal]:
        self._require_running()
        before = len(self._context.emitted_signals)
        start = perf_counter()
        try:
            callback(self._context, event)
        except Exception as exc:  # noqa: BLE001 - isolate strategy fault
            self._fail(str(exc))
            logger.warning("strategy %s failed: %s", self._identity.code, exc)
            return []
        finally:
            self._metrics.record_callback(perf_counter() - start)

        accepted: list[StrategySignal] = []
        for signal in self._context.emitted_signals[before:]:
            result = self._validator.validate(
                signal,
                self._identity,
                allowed_instruments=self._allowed_instruments,
                event_timestamp=event_timestamp,
            )
            if not result.valid:
                self._metrics.inc("signals_rejected")
                logger.warning(
                    "strategy %s rejected signal: %s", self._identity.code, result.reason
                )
                continue
            if self._deduplicator.is_duplicate(signal, event_timestamp):
                self._metrics.inc("signals_duplicate")
                continue
            accepted.append(signal)
            self._metrics.inc("signals_generated")

        # Bound the context buffer: keep only this event's signals so the list
        # cannot grow unbounded over a long-running strategy.
        del self._context.emitted_signals[:before]
        return accepted

    def _fail(self, reason: str) -> None:
        if self._state.is_terminal:
            return
        self._state.transition(StrategyRunState.FAILED)
        self._fail_reason = reason
        self._metrics.inc("strategies_failed")
