from __future__ import annotations

import time
from uuid import uuid4

from alpha_algo_strategy_engine import StrategyRuntime, TradingMode
from strategy_test_support import (
    RecordingStrategy,
    make_definition,
    make_identity,
    make_tick,
)


class SlowStrategy(RecordingStrategy):
    def on_tick(self, context, tick) -> None:
        time.sleep(1.0)


def test_one_strategy_failure_does_not_stop_others() -> None:
    ident_a = make_identity(code="a")
    ident_b = make_identity(code="b")
    instr_a = uuid4()
    instr_b = uuid4()

    failing = RecordingStrategy()
    failing.raise_on = "on_tick"
    healthy = RecordingStrategy()

    runtime = StrategyRuntime()
    runtime.register(make_definition(identity=ident_a, factory=lambda: failing, instruments=frozenset({instr_a})))
    runtime.register(make_definition(identity=ident_b, factory=lambda: healthy, instruments=frozenset({instr_b})))
    runtime.start(ident_a.strategy_id, TradingMode.PAPER)
    runtime.start(ident_b.strategy_id, TradingMode.PAPER)

    # a tick for A makes A fail; B is untouched and still RUNNING
    runtime.on_tick(make_tick(instrument_id=instr_a))
    runtime.on_tick(make_tick(instrument_id=instr_b))

    assert runtime.status(ident_a.strategy_id)["state"] == "failed"
    assert runtime.status(ident_b.strategy_id)["state"] == "running"
    assert healthy.calls.count("on_tick") == 1


def test_strategy_timeout_is_isolated() -> None:
    ident = make_identity(code="slow")
    instr = uuid4()
    slow = SlowStrategy()

    runtime = StrategyRuntime(callback_timeout_seconds=0.05, max_workers=2)
    runtime.register(make_definition(identity=ident, factory=lambda: slow, instruments=frozenset({instr})))
    runtime.start(ident.strategy_id, TradingMode.PAPER)

    runtime.on_tick(make_tick(instrument_id=instr))
    assert runtime.status(ident.strategy_id)["state"] == "failed"
    runtime.shutdown()
