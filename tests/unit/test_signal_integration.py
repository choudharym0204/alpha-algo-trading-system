"""Phase 4 Strategy Runtime → Phase 5 Signal Engine boundary (integration)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from signal_test_support import FakeSessionFactory
from strategy_test_support import (
    RecordingStrategy,
    make_definition,
    make_identity,
    make_signal,
    make_tick,
)

from alpha_algo_signal_engine.boundary import build_signal_engine, connect_strategy_runtime
from alpha_algo_signal_engine.repository import SignalRepository
from alpha_algo_signal_engine.service import SignalEngine
from alpha_algo_strategy_engine import StrategyRuntime, TradingMode
from alpha_algo_strategy_engine.errors import TradingModeError as StrategyTradingModeError


def test_phase4_to_phase5_boundary_persists_signal() -> None:
    instr = uuid4()
    identity = make_identity()
    strategy = RecordingStrategy()
    strategy.signals_to_emit = [
        make_signal(
            strategy_id=identity.strategy_id,
            version=identity.version,
            config_hash=identity.config_hash,
            instrument_id=instr,
        )
    ]

    runtime = StrategyRuntime()
    runtime.register(
        make_definition(identity=identity, factory=lambda: strategy, instruments=frozenset({instr}))
    )
    runtime.start(identity.strategy_id, TradingMode.PAPER)

    factory = FakeSessionFactory()
    engine = build_signal_engine(runtime, factory)

    runtime.on_tick(make_tick(instrument_id=instr))

    assert engine.metrics.signals_received >= 1
    assert engine.metrics.signals_persisted == 1
    assert engine.metrics.signals_accepted == 1

    persisted = [obj for session in factory.sessions for obj in session.added]
    assert len(persisted) == 1
    orm = persisted[0]
    assert orm.strategy_id == identity.strategy_id
    assert orm.instrument_id == instr
    assert orm.action == "BUY"
    assert orm.state == "persisted"
    assert orm.config_hash == identity.config_hash
    assert orm.strategy_version == identity.version


def test_replayed_event_is_deduplicated_before_engine() -> None:
    instr = uuid4()
    identity = make_identity()
    strategy = RecordingStrategy()
    strategy.signals_to_emit = [
        make_signal(
            strategy_id=identity.strategy_id,
            version=identity.version,
            config_hash=identity.config_hash,
            instrument_id=instr,
        )
    ]

    runtime = StrategyRuntime()
    runtime.register(
        make_definition(identity=identity, factory=lambda: strategy, instruments=frozenset({instr}))
    )
    runtime.start(identity.strategy_id, TradingMode.PAPER)
    engine = build_signal_engine(runtime, FakeSessionFactory())

    tick = make_tick(instrument_id=instr)
    runtime.on_tick(tick)
    runtime.on_tick(tick)  # same event → Phase 4 in-memory dedup drops it first

    assert engine.metrics.signals_received == 1
    assert engine.metrics.signals_persisted == 1
    assert engine.metrics.signals_duplicate == 0


def test_connect_strategy_runtime_wires_existing_engine() -> None:
    instr = uuid4()
    identity = make_identity()
    strategy = RecordingStrategy()
    strategy.signals_to_emit = [
        make_signal(
            strategy_id=identity.strategy_id,
            version=identity.version,
            config_hash=identity.config_hash,
            instrument_id=instr,
        )
    ]

    runtime = StrategyRuntime()
    runtime.register(
        make_definition(identity=identity, factory=lambda: strategy, instruments=frozenset({instr}))
    )
    runtime.start(identity.strategy_id, TradingMode.PAPER)

    engine = SignalEngine(
        directory=None,  # replaced by connect_strategy_runtime
        repository=SignalRepository(FakeSessionFactory()),
    )
    connect_strategy_runtime(runtime, engine)
    runtime.on_tick(make_tick(instrument_id=instr))
    assert engine.metrics.signals_persisted == 1


def test_live_still_blocked_at_runtime_boundary() -> None:
    identity = make_identity()
    runtime = StrategyRuntime()
    runtime.register(make_definition(identity=identity))
    with pytest.raises(StrategyTradingModeError):
        runtime.start(identity.strategy_id, TradingMode.LIVE)
