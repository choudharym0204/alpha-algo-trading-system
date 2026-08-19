from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from alpha_algo_strategy_engine import (
    SignalDeduplicator,
    StrategyRuntime,
    TradingMode,
    signal_dedup_key,
)
from strategy_test_support import (
    RecordingStrategy,
    make_definition,
    make_identity,
    make_signal,
    make_tick,
)


def test_dedup_key_is_deterministic() -> None:
    identity = make_identity()
    signal = make_signal(
        strategy_id=identity.strategy_id, version="1.0.0", config_hash=identity.config_hash
    )
    ts = datetime.now(UTC)
    assert signal_dedup_key(signal, ts) == signal_dedup_key(signal, ts)
    assert signal_dedup_key(signal, ts) != signal_dedup_key(signal, ts + timedelta(seconds=1))


def test_deduplicator_detects_replay() -> None:
    identity = make_identity()
    signal = make_signal(
        strategy_id=identity.strategy_id, version="1.0.0", config_hash=identity.config_hash
    )
    ts = datetime.now(UTC)
    dedup = SignalDeduplicator()
    assert dedup.is_duplicate(signal, ts) is False
    assert dedup.is_duplicate(signal, ts) is True  # same event replay
    assert dedup.is_duplicate(signal, ts + timedelta(seconds=1)) is False  # new event


def test_deduplicator_is_bounded() -> None:
    identity = make_identity()
    dedup = SignalDeduplicator(maxsize=3)
    ts = datetime.now(UTC)
    for i in range(5):
        signal = make_signal(
            strategy_id=identity.strategy_id,
            version="1.0.0",
            config_hash=identity.config_hash,
            instrument_id=uuid4(),
        )
        dedup.is_duplicate(signal, ts)
    assert len(dedup) == 3


def test_runtime_dedups_replayed_event() -> None:
    identity = make_identity()
    instr = uuid4()
    strategy = RecordingStrategy()
    strategy.signals_to_emit = [
        make_signal(
            strategy_id=identity.strategy_id,
            version="1.0.0",
            config_hash=identity.config_hash,
            instrument_id=instr,
        )
    ]
    runtime = StrategyRuntime()
    runtime.register(
        make_definition(identity=identity, factory=lambda: strategy, instruments=frozenset({instr}))
    )
    runtime.start(identity.strategy_id, TradingMode.PAPER)

    # replay the same tick twice -> only one accepted signal
    tick = make_tick(instrument_id=instr)
    first = runtime.on_tick(tick)
    second = runtime.on_tick(tick)
    assert len(first) == 1
    assert len(second) == 0
    assert runtime.metrics.signals_duplicate == 1
