"""Regression tests for Phase-4 review findings (adversarial review fixes).

Each test locks in a concrete fix for an issue found by the 4-dimension review:
- spoof-proof traceability enrichment (direct assignment, not setdefault)
- order/position runtime entry points + routing
- shutdown does not block on a hung callback (wait=False + cancel)
- deep immutability of nested config
- stale-signal rejection against the authoritative event time
- registry.load rejects a non-strategy factory
- failure reason surfaced into the run record
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from alpha_algo_strategy_engine import (
    ConfigValidationError,
    StrategyInstance,
    StrategyRuntime,
    TradingMode,
)
from alpha_algo_strategy_engine.registry import StrategyRegistry
from alpha_algo_strategy_engine.state import StrategyRunState
from alpha_algo_strategies import OrderUpdate, PositionUpdate
from strategy_test_support import (
    RecordingStrategy,
    make_definition,
    make_identity,
    make_signal,
    make_tick,
)


def test_enrich_overwrites_spoofed_traceability_metadata() -> None:
    identity = make_identity()
    instr = uuid4()
    strategy = RecordingStrategy()
    signal = make_signal(
        strategy_id=identity.strategy_id,
        version="1.0.0",
        config_hash=identity.config_hash,
        instrument_id=instr,
    ).model_copy(
        update={
            "metadata": {
                "strategy_code_hash": "FAKE",
                "strategy_run_id": "FAKE",
                "event_timestamp": "FAKE",
            }
        }
    )
    strategy.signals_to_emit = [signal]

    runtime = StrategyRuntime()
    runtime.register(
        make_definition(identity=identity, factory=lambda: strategy, instruments=frozenset({instr}))
    )
    runtime.start(identity.strategy_id, TradingMode.PAPER)

    signals = runtime.on_tick(make_tick(instrument_id=instr))
    assert len(signals) == 1
    meta = signals[0].metadata
    assert meta["strategy_code_hash"] == identity.code_hash  # spoof overwritten
    assert meta["strategy_run_id"] != "FAKE"
    assert meta["event_timestamp"] != "FAKE"


def test_order_and_position_updates_route_to_strategy() -> None:
    identity = make_identity()
    instr = uuid4()
    strategy = RecordingStrategy()

    runtime = StrategyRuntime()
    runtime.register(
        make_definition(identity=identity, factory=lambda: strategy, instruments=frozenset({instr}))
    )
    runtime.start(identity.strategy_id, TradingMode.PAPER)

    order = OrderUpdate(order_id=uuid4(), instrument_id=instr, status="FILLED", timestamp=datetime.now(UTC))
    position = PositionUpdate(
        position_id=uuid4(), instrument_id=instr, quantity=Decimal("10"), timestamp=datetime.now(UTC)
    )

    assert runtime.on_order_update(order) == []
    assert runtime.on_position_update(position) == []
    assert "on_order_update" in strategy.calls
    assert "on_position_update" in strategy.calls


def test_shutdown_returns_without_waiting_for_hung_callback() -> None:
    class Hung(RecordingStrategy):
        def on_tick(self, context, tick) -> None:
            time.sleep(0.5)

    identity = make_identity(code="hung")
    instr = uuid4()

    runtime = StrategyRuntime(callback_timeout_seconds=0.05, max_workers=2)
    runtime.register(
        make_definition(identity=identity, factory=lambda: Hung(), instruments=frozenset({instr}))
    )
    runtime.start(identity.strategy_id, TradingMode.PAPER)
    runtime.on_tick(make_tick(instrument_id=instr))  # times out -> FAILED

    start = time.monotonic()
    runtime.shutdown()
    assert time.monotonic() - start < 0.4  # shutdown must not wait ~0.5s for the callback


def test_config_nested_values_are_deeply_immutable() -> None:
    nested = {"window": [1, 2, 3]}
    identity = make_identity(config={"nested": nested})
    definition = make_definition(identity=identity, config={"nested": nested})
    instance = StrategyInstance(definition, RecordingStrategy())

    # Mutating the ORIGINAL nested structure must not affect the instance.
    nested["window"].append(999)
    assert list(instance.context.config["nested"]["window"]) == [1, 2, 3]
    # The instance's nested config is itself read-only.
    with pytest.raises(TypeError):
        instance.context.config["nested"]["window"] = (4, 5)  # type: ignore[index]


def test_stale_signal_rejected_against_event_time() -> None:
    identity = make_identity()
    instr = uuid4()
    strategy = RecordingStrategy()
    now = datetime.now(UTC)
    strategy.signals_to_emit = [
        make_signal(
            strategy_id=identity.strategy_id,
            version="1.0.0",
            config_hash=identity.config_hash,
            instrument_id=instr,
            timestamp=now - timedelta(seconds=60),
        )
    ]

    runtime = StrategyRuntime()
    runtime.register(
        make_definition(identity=identity, factory=lambda: strategy, instruments=frozenset({instr}))
    )
    runtime.start(identity.strategy_id, TradingMode.PAPER)

    assert runtime.on_tick(make_tick(instrument_id=instr, timestamp=now)) == []


def test_registry_load_rejects_non_strategy_factory() -> None:
    identity = make_identity()
    registry = StrategyRegistry()
    registry.register(make_definition(identity=identity, factory=lambda: "not a strategy"))
    with pytest.raises(TypeError):
        registry.load(identity.strategy_id)


def test_failed_strategy_reason_surfaced_in_record() -> None:
    identity = make_identity(code="boom")
    instr = uuid4()
    failing = RecordingStrategy()
    failing.raise_on = "on_tick"

    runtime = StrategyRuntime()
    runtime.register(
        make_definition(identity=identity, factory=lambda: failing, instruments=frozenset({instr}))
    )
    runtime.start(identity.strategy_id, TradingMode.PAPER)
    runtime.on_tick(make_tick(instrument_id=instr))

    record = runtime.run_record(identity.strategy_id)
    assert record.state == StrategyRunState.FAILED
    assert record.reason is not None and "boom in on_tick" in record.reason
