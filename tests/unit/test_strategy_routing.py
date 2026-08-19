from __future__ import annotations

from uuid import uuid4

from alpha_algo_contracts import CandleTimeframe
from alpha_algo_strategy_engine import StrategyDispatcher, StrategyInstance
from strategy_test_support import (
    RecordingStrategy,
    make_candle,
    make_definition,
    make_identity,
    make_tick,
)


def _running_instance(code: str, instruments=frozenset(), timeframes=frozenset()):
    identity = make_identity(code=code)
    definition = make_definition(
        identity=identity, instruments=frozenset(instruments), timeframes=frozenset(timeframes)
    )
    instance = StrategyInstance(definition, RecordingStrategy())
    instance.initialize()
    instance.start()
    return instance, definition


def test_route_by_instrument() -> None:
    instr_a = uuid4()
    dispatcher = StrategyDispatcher()
    instance, definition = _running_instance("a", instruments={instr_a})
    dispatcher.register(instance, definition)

    assert dispatcher.match_tick(make_tick(instrument_id=instr_a)) == [instance]
    assert dispatcher.match_tick(make_tick(instrument_id=uuid4())) == []


def test_route_all_instruments_when_unrestricted() -> None:
    dispatcher = StrategyDispatcher()
    instance, definition = _running_instance("a")  # empty instruments = all
    dispatcher.register(instance, definition)
    assert dispatcher.match_tick(make_tick(instrument_id=uuid4())) == [instance]


def test_disabled_strategy_not_routed() -> None:
    instr = uuid4()
    dispatcher = StrategyDispatcher()
    instance, definition = _running_instance("a", instruments={instr})
    dispatcher.register(instance, definition)
    dispatcher.set_enabled(definition.identity.strategy_id, False)
    assert dispatcher.match_tick(make_tick(instrument_id=instr)) == []


def test_multiple_strategies_isolated_routing() -> None:
    instr_a = uuid4()
    instr_b = uuid4()
    dispatcher = StrategyDispatcher()
    inst_a, def_a = _running_instance("a", instruments={instr_a})
    inst_b, def_b = _running_instance("b", instruments={instr_b})
    dispatcher.register(inst_a, def_a)
    dispatcher.register(inst_b, def_b)

    assert dispatcher.match_tick(make_tick(instrument_id=instr_a)) == [inst_a]
    assert dispatcher.match_tick(make_tick(instrument_id=instr_b)) == [inst_b]
    # a tick for a third instrument reaches nobody
    assert dispatcher.match_tick(make_tick(instrument_id=uuid4())) == []


def test_route_candle_by_timeframe() -> None:
    instr = uuid4()
    dispatcher = StrategyDispatcher()
    instance, definition = _running_instance(
        "a", instruments={instr}, timeframes={CandleTimeframe.ONE_MINUTE}
    )
    dispatcher.register(instance, definition)

    candle_1m = make_candle(instrument_id=instr, timeframe=CandleTimeframe.ONE_MINUTE)
    candle_1h = make_candle(instrument_id=instr, timeframe=CandleTimeframe.ONE_HOUR)
    assert dispatcher.match_candle(candle_1m) == [instance]
    assert dispatcher.match_candle(candle_1h) == []
