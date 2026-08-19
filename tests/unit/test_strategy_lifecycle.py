from __future__ import annotations

from uuid import uuid4

import pytest

from alpha_algo_strategy_engine import (
    LifecycleError,
    StrategyInstance,
    StrategyRunState,
)
from strategy_test_support import (
    RecordingStrategy,
    make_candle,
    make_definition,
    make_identity,
    make_tick,
)


def _instance(strategy: RecordingStrategy | None = None, instruments=frozenset()):
    identity = make_identity()
    definition = make_definition(identity=identity, instruments=frozenset(instruments))
    return identity, StrategyInstance(definition, strategy or RecordingStrategy())


def test_full_lifecycle_flow() -> None:
    _, instance = _instance()
    instance.initialize()
    instance.start()
    assert instance.state == StrategyRunState.RUNNING
    instance.on_tick(make_tick())
    instance.on_candle(make_candle())
    instance.pause()
    assert instance.state == StrategyRunState.PAUSED
    instance.resume()
    assert instance.state == StrategyRunState.RUNNING
    instance.stop()
    assert instance.state == StrategyRunState.STOPPED


def test_on_tick_before_initialize_rejected() -> None:
    _, instance = _instance()
    with pytest.raises(LifecycleError):
        instance.on_tick(make_tick())


def test_on_tick_before_start_rejected() -> None:
    _, instance = _instance()
    instance.initialize()
    with pytest.raises(LifecycleError):
        instance.on_tick(make_tick())


def test_start_twice_rejected() -> None:
    _, instance = _instance()
    instance.initialize()
    instance.start()
    with pytest.raises(LifecycleError, match="start only allowed once"):
        instance.start()


def test_stop_before_start_rejected() -> None:
    _, instance = _instance()
    instance.initialize()
    with pytest.raises(LifecycleError, match="stop only allowed"):
        instance.stop()


def test_duplicate_shutdown_rejected() -> None:
    _, instance = _instance()
    instance.initialize()
    instance.start()
    instance.stop()
    with pytest.raises(LifecycleError):
        instance.stop()


def test_callbacks_after_stop_rejected() -> None:
    _, instance = _instance()
    instance.initialize()
    instance.start()
    instance.stop()
    with pytest.raises(LifecycleError):
        instance.on_tick(make_tick())


def test_strategy_exception_marks_failed_and_isolated() -> None:
    strategy = RecordingStrategy()
    strategy.raise_on = "on_tick"
    _, instance = _instance(strategy)
    instance.initialize()
    instance.start()
    signals = instance.on_tick(make_tick())
    assert signals == []
    assert instance.state == StrategyRunState.FAILED
    assert instance.fail_reason is not None
    assert instance.metrics.strategies_failed == 1
