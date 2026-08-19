from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from alpha_algo_market_data import EventKind, IngestStatus, MarketDataEngine, RawMarketEvent
from alpha_algo_strategy_engine import StrategyRuntime, TradingMode, connect_market_data
from strategy_test_support import (
    RecordingStrategy,
    make_definition,
    make_identity,
    make_signal,
)


def _raw_tick_event(instrument_id, timestamp: datetime) -> RawMarketEvent:
    return RawMarketEvent(
        provider="fake",
        kind=EventKind.TICK,
        payload={
            "instrument_id": instrument_id,
            "exchange": "NSE",
            "symbol": "RELIANCE",
            "timestamp": timestamp,
            "ltp": "2450.25",
            "source_broker": "fake",
            "source_sequence": "seq-1",
        },
        received_at=timestamp,
    )


def test_phase3_to_phase4_boundary() -> None:
    """MarketDataEngine (Phase 3) → normalized tick → StrategyRuntime (Phase 4) → signal."""
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

    runtime = StrategyRuntime()
    runtime.register(
        make_definition(identity=identity, factory=lambda: strategy, instruments=frozenset({instr}))
    )
    runtime.start(identity.strategy_id, TradingMode.PAPER)

    engine = MarketDataEngine(clock=lambda: datetime.now(UTC), max_age=timedelta(seconds=5))
    connect_market_data(engine, runtime)  # wires engine → runtime consumers

    captured: list = []
    runtime.add_signal_consumer(captured.append)

    now = datetime.now(UTC)
    result = engine.ingest_raw(_raw_tick_event(instr, now - timedelta(seconds=1)))

    assert result.status == IngestStatus.ACCEPTED
    assert len(captured) == 1
    signal = captured[0]
    assert signal.strategy_id == identity.strategy_id
    assert signal.instrument_id == instr
    assert signal.metadata["strategy_code_hash"] == identity.code_hash
