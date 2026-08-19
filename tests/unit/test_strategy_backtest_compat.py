from __future__ import annotations

from uuid import uuid4

from alpha_algo_strategy_engine import StrategyRuntime, TradingMode
from strategy_test_support import (
    RecordingStrategy,
    make_definition,
    make_identity,
    make_signal,
    make_tick,
)


def test_backtest_mode_runs_without_db_or_network() -> None:
    """The runtime must produce signals with no network/live provider/Postgres."""
    instr = uuid4()
    identity = make_identity()
    strategy = RecordingStrategy()
    strategy.signals_to_emit = [
        make_signal(
            strategy_id=identity.strategy_id,
            version="1.0.0",
            config_hash=identity.config_hash,
            instrument_id=instr,
        )
    ]

    runtime = StrategyRuntime()  # no DB, no network, no provider
    runtime.register(
        make_definition(identity=identity, factory=lambda: strategy, instruments=frozenset({instr}))
    )
    run_id = runtime.start(identity.strategy_id, TradingMode.BACKTEST)

    signals = runtime.on_tick(make_tick(instrument_id=instr))
    assert len(signals) == 1

    record = runtime.run_record(identity.strategy_id)
    assert record.run_id == run_id
    assert record.trading_mode == TradingMode.BACKTEST
    assert record.strategy_id == identity.strategy_id
    assert record.version == identity.version
    assert record.config_hash == identity.config_hash
    assert record.code_hash == identity.code_hash


def test_run_record_tracks_full_identity() -> None:
    identity = make_identity(version="2.3.4")
    runtime = StrategyRuntime()
    runtime.register(make_definition(identity=identity))
    runtime.start(identity.strategy_id, TradingMode.PAPER)
    record = runtime.run_record(identity.strategy_id)
    assert record.version == "2.3.4"
    assert record.config_hash == identity.config_hash
    assert record.code_hash == identity.code_hash
    assert record.started_at is not None
