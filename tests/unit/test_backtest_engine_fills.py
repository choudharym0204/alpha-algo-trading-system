from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from alpha_algo_contracts import CandleTimeframe, MarketCandle, MarketTick

from alpha_algo_backtest_engine import (
    CostModel,
    IntentSide,
    IntentType,
    OrderIntent,
    UnfilledReason,
    run_backtest,
)
from alpha_algo_backtesting import BacktestInput

INSTRUMENT = UUID("00000000-0000-0000-0000-000000000001")


def utc(y: int, mo: int, d: int, h: int = 9, mi: int = 0, s: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, s, tzinfo=timezone.utc)


def tick(ts: datetime, ltp: str, bid: str | None = None, ask: str | None = None) -> MarketTick:
    return MarketTick(
        instrument_id=INSTRUMENT,
        exchange="NSE",
        symbol="TEST",
        timestamp=ts,
        ltp=Decimal(ltp),
        bid=Decimal(bid) if bid is not None else None,
        ask=Decimal(ask) if ask is not None else None,
        source_broker="unit",
        source_sequence=f"seq-{ts.isoformat()}",
        received_at=ts,
    )


def candle(ts: datetime, open_price: str, high: str, low: str, close: str) -> MarketCandle:
    return MarketCandle(
        instrument_id=INSTRUMENT,
        exchange="NSE",
        symbol="TEST",
        timeframe=CandleTimeframe.ONE_MINUTE,
        candle_start=ts,
        open_price=Decimal(open_price),
        high_price=Decimal(high),
        low_price=Decimal(low),
        close_price=Decimal(close),
        source_broker="unit",
        generated_at=ts,
    )


def make_input(records: tuple) -> BacktestInput:
    return BacktestInput(dataset_id="ds", source="unit", records=records)


def order(
    side: IntentSide,
    order_type: IntentType,
    decided_at: datetime,
    quantity: str = "10",
    limit_price: str | None = None,
) -> OrderIntent:
    return OrderIntent(
        side=side,
        order_type=order_type,
        quantity=Decimal(quantity),
        decided_at=decided_at,
        limit_price=Decimal(limit_price) if limit_price is not None else None,
    )


def run(records: tuple, *intents: OrderIntent) -> object:
    return run_backtest(
        inputs=make_input(records),
        intents=tuple(intents),
        cost_model=CostModel(commission_per_fill=Decimal("0"), slippage_bps=Decimal("0")),
        initial_capital=Decimal("100000"),
    )


class TestMarketFillsOnTicks:
    def test_market_buy_fills_at_ask_not_ltp(self) -> None:
        records = (
            tick(utc(2026, 1, 1, 9, 0), "100", "99.5", "100.5"),
            tick(utc(2026, 1, 1, 9, 1), "100", "99.5", "100.5"),
        )
        result = run(records, order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 30)))
        (fill,) = result.fills
        assert fill.anchor_price == Decimal("100.5")
        assert fill.fill_price == Decimal("100.5")

    def test_market_sell_fills_at_bid_not_ltp(self) -> None:
        records = (
            tick(utc(2026, 1, 1, 9, 0), "100", "99.5", "100.5"),
            tick(utc(2026, 1, 1, 9, 1), "100", "99.5", "100.5"),
            tick(utc(2026, 1, 1, 9, 2), "100", "99.5", "100.5"),
        )
        result = run(
            records,
            order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 20)),
            order(IntentSide.SELL, IntentType.MARKET, utc(2026, 1, 1, 9, 1, 30)),
        )
        (sell_fill,) = [f for f in result.fills if f.side is IntentSide.SELL]
        assert sell_fill.anchor_price == Decimal("99.5")
        assert sell_fill.fill_price == Decimal("99.5")

    def test_market_buy_falls_back_to_ltp_when_ask_absent(self) -> None:
        records = (
            tick(utc(2026, 1, 1, 9, 0), "100"),
            tick(utc(2026, 1, 1, 9, 1), "101"),
        )
        result = run(records, order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 30)))
        (fill,) = result.fills
        assert fill.anchor_price == Decimal("101")

    def test_market_sell_falls_back_to_ltp_when_bid_absent(self) -> None:
        records = (
            tick(utc(2026, 1, 1, 9, 0), "100"),
            tick(utc(2026, 1, 1, 9, 1), "100"),
            tick(utc(2026, 1, 1, 9, 2), "101"),
        )
        result = run(
            records,
            order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 20)),
            order(IntentSide.SELL, IntentType.MARKET, utc(2026, 1, 1, 9, 1, 30)),
        )
        (sell_fill,) = [f for f in result.fills if f.side is IntentSide.SELL]
        assert sell_fill.anchor_price == Decimal("101")


class TestLimitFillsOnTicks:
    def test_limit_buy_fills_at_ask_when_crossed(self) -> None:
        records = (
            tick(utc(2026, 1, 1, 9, 0), "100", "99.5", "100.5"),
            tick(utc(2026, 1, 1, 9, 1), "100", "99.5", "100.5"),
        )
        result = run(
            records,
            order(IntentSide.BUY, IntentType.LIMIT, utc(2026, 1, 1, 9, 0, 30), limit_price="101"),
        )
        (fill,) = result.fills
        assert fill.anchor_price == Decimal("100.5")
        assert fill.fill_price == Decimal("100.5")

    def test_limit_buy_not_crossed_is_unfilled(self) -> None:
        records = (
            tick(utc(2026, 1, 1, 9, 0), "100", "99.5", "100.5"),
            tick(utc(2026, 1, 1, 9, 1), "100", "99.5", "100.5"),
        )
        result = run(
            records,
            order(IntentSide.BUY, IntentType.LIMIT, utc(2026, 1, 1, 9, 0, 30), limit_price="100"),
        )
        (outcome,) = result.outcomes
        assert not outcome.filled
        assert outcome.reason == UnfilledReason.LIMIT_NOT_EXECUTABLE.value

    def test_limit_sell_fills_at_bid_when_crossed(self) -> None:
        records = (
            tick(utc(2026, 1, 1, 9, 0), "100", "99.5", "100.5"),
            tick(utc(2026, 1, 1, 9, 1), "100", "99.5", "100.5"),
            tick(utc(2026, 1, 1, 9, 2), "100", "99.5", "100.5"),
        )
        result = run(
            records,
            order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 20)),
            order(IntentSide.SELL, IntentType.LIMIT, utc(2026, 1, 1, 9, 1, 30), limit_price="99"),
        )
        (sell_fill,) = [f for f in result.fills if f.side is IntentSide.SELL]
        assert sell_fill.anchor_price == Decimal("99.5")
        assert sell_fill.fill_price == Decimal("99.5")

    def test_limit_sell_not_crossed_is_unfilled(self) -> None:
        records = (
            tick(utc(2026, 1, 1, 9, 0), "100", "99.5", "100.5"),
            tick(utc(2026, 1, 1, 9, 1), "100", "99.5", "100.5"),
        )
        result = run(
            records,
            order(IntentSide.SELL, IntentType.LIMIT, utc(2026, 1, 1, 9, 0, 30), limit_price="100"),
        )
        (outcome,) = result.outcomes
        assert not outcome.filled
        assert outcome.reason == UnfilledReason.LIMIT_NOT_EXECUTABLE.value

    def test_limit_buy_with_missing_ask_never_falls_back_to_ltp(self) -> None:
        records = (
            tick(utc(2026, 1, 1, 9, 0), "100"),
            tick(utc(2026, 1, 1, 9, 1), "101"),
        )
        result = run(
            records,
            order(IntentSide.BUY, IntentType.LIMIT, utc(2026, 1, 1, 9, 0, 30), limit_price="105"),
        )
        (outcome,) = result.outcomes
        assert not outcome.filled
        assert outcome.reason == UnfilledReason.NO_EXECUTABLE_ASK.value
        assert result.fills == ()

    def test_limit_sell_with_missing_bid_never_falls_back_to_ltp(self) -> None:
        records = (
            tick(utc(2026, 1, 1, 9, 0), "100"),
            tick(utc(2026, 1, 1, 9, 1), "101"),
        )
        result = run(
            records,
            order(IntentSide.SELL, IntentType.LIMIT, utc(2026, 1, 1, 9, 0, 30), limit_price="95"),
        )
        (outcome,) = result.outcomes
        assert not outcome.filled
        assert outcome.reason == UnfilledReason.NO_EXECUTABLE_BID.value


class TestFillsOnCandles:
    def test_market_fills_at_next_open(self) -> None:
        records = (
            candle(utc(2026, 1, 1, 9, 0), "100", "105", "99", "104"),
            candle(utc(2026, 1, 1, 9, 1), "101", "106", "100", "105"),
        )
        result = run(records, order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 30)))
        (fill,) = result.fills
        assert fill.anchor_price == Decimal("101")
        assert fill.fill_price == Decimal("101")
        assert fill.record_index == 1

    def test_intent_decided_at_candle_start_fills_next_candle(self) -> None:
        # decided_at == candle 0 start => first record STRICTLY after is candle 1.
        records = (
            candle(utc(2026, 1, 1, 9, 0), "100", "105", "99", "104"),
            candle(utc(2026, 1, 1, 9, 1), "101", "106", "100", "105"),
        )
        result = run(records, order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0)))
        (fill,) = result.fills
        assert fill.record_index == 1
        assert fill.fill_price == Decimal("101")

    def test_limit_buy_fills_at_open_when_crossed(self) -> None:
        records = (
            candle(utc(2026, 1, 1, 9, 0), "100", "105", "99", "104"),
            candle(utc(2026, 1, 1, 9, 1), "101", "106", "100", "105"),
        )
        result = run(
            records,
            order(IntentSide.BUY, IntentType.LIMIT, utc(2026, 1, 1, 9, 0, 30), limit_price="102"),
        )
        (fill,) = result.fills
        assert fill.fill_price == Decimal("101")

    def test_limit_buy_below_open_is_unfilled_even_if_low_touches(self) -> None:
        # Intra-bar touch is deliberately not modeled (CANDLE_LIMIT_NO_IMPROVEMENT):
        # the bar's low (100) is below the limit but the OPEN (101) is not.
        records = (
            candle(utc(2026, 1, 1, 9, 0), "100", "105", "99", "104"),
            candle(utc(2026, 1, 1, 9, 1), "101", "106", "100", "105"),
        )
        result = run(
            records,
            order(IntentSide.BUY, IntentType.LIMIT, utc(2026, 1, 1, 9, 0, 30), limit_price="100.5"),
        )
        (outcome,) = result.outcomes
        assert not outcome.filled
        assert outcome.reason == UnfilledReason.LIMIT_NOT_EXECUTABLE.value

    def test_limit_sell_fills_at_open_when_crossed(self) -> None:
        records = (
            candle(utc(2026, 1, 1, 9, 0), "100", "105", "99", "104"),
            candle(utc(2026, 1, 1, 9, 1), "101", "106", "100", "105"),
            candle(utc(2026, 1, 1, 9, 2), "102", "107", "101", "106"),
        )
        result = run(
            records,
            order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 20)),
            order(IntentSide.SELL, IntentType.LIMIT, utc(2026, 1, 1, 9, 1, 20), limit_price="100"),
        )
        (sell_fill,) = [f for f in result.fills if f.side is IntentSide.SELL]
        assert sell_fill.fill_price == Decimal("102")

    def test_limit_sell_above_open_is_unfilled_even_if_high_touches(self) -> None:
        records = (
            candle(utc(2026, 1, 1, 9, 0), "100", "105", "99", "104"),
            candle(utc(2026, 1, 1, 9, 1), "101", "106", "100", "105"),
        )
        result = run(
            records,
            order(IntentSide.SELL, IntentType.LIMIT, utc(2026, 1, 1, 9, 0, 30), limit_price="105"),
        )
        (outcome,) = result.outcomes
        assert not outcome.filled
        assert outcome.reason == UnfilledReason.LIMIT_NOT_EXECUTABLE.value


class TestTimingAndAccounting:
    def test_no_record_after_decision_is_unfilled(self) -> None:
        records = (tick(utc(2026, 1, 1, 9, 0), "100", "99.5", "100.5"),)
        result = run(records, order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 30)))
        (outcome,) = result.outcomes
        assert not outcome.filled
        assert outcome.reason == UnfilledReason.NO_RECORD_AFTER_DECISION.value

    def test_intent_at_last_record_is_unfilled(self) -> None:
        records = (
            tick(utc(2026, 1, 1, 9, 0), "100", "99.5", "100.5"),
            tick(utc(2026, 1, 1, 9, 1), "101", "100.5", "101.5"),
        )
        result = run(records, order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 1)))
        (outcome,) = result.outcomes
        assert not outcome.filled
        assert outcome.reason == UnfilledReason.NO_RECORD_AFTER_DECISION.value

    def test_sell_beyond_position_is_rejected(self) -> None:
        records = (
            tick(utc(2026, 1, 1, 9, 0), "100", "99.5", "100.5"),
            tick(utc(2026, 1, 1, 9, 1), "101", "100.5", "101.5"),
        )
        result = run(records, order(IntentSide.SELL, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 30)))
        (outcome,) = result.outcomes
        assert not outcome.filled
        assert outcome.reason == UnfilledReason.INSUFFICIENT_POSITION.value

    def test_full_or_nothing_quantity(self) -> None:
        records = (
            tick(utc(2026, 1, 1, 9, 0), "100", "99.5", "100.5"),
            tick(utc(2026, 1, 1, 9, 1), "101", "100.5", "101.5"),
        )
        result = run(
            records,
            order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 30), quantity="25"),
        )
        (fill,) = result.fills
        assert fill.quantity == Decimal("25")

    def test_same_anchor_intents_apply_in_decided_at_order(self) -> None:
        # Both intents decided between record 0 and record 1; BUY fills first,
        # so the SELL (which needs the position) also fills.
        records = (
            tick(utc(2026, 1, 1, 9, 0), "100", "99.5", "100.5"),
            tick(utc(2026, 1, 1, 9, 1), "101", "100.5", "101.5"),
        )
        buy = order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 20))
        sell = order(IntentSide.SELL, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 40))
        result = run(records, buy, sell)
        assert len(result.fills) == 2
        assert all(outcome.filled for outcome in result.outcomes)

    def test_outcomes_are_one_to_one_with_intents(self) -> None:
        records = (
            tick(utc(2026, 1, 1, 9, 0), "100", "99.5", "100.5"),
            tick(utc(2026, 1, 1, 9, 1), "101", "100.5", "101.5"),
        )
        intents = (
            order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 20)),
            order(IntentSide.SELL, IntentType.LIMIT, utc(2026, 1, 1, 9, 0, 40), limit_price="150"),
            order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 1, 20)),
        )
        result = run(records, *intents)
        assert len(result.outcomes) == 3
        assert [o.filled for o in result.outcomes] == [True, False, False]
        assert [o.reason for o in result.outcomes][1] == UnfilledReason.LIMIT_NOT_EXECUTABLE.value
        assert [o.reason for o in result.outcomes][2] == UnfilledReason.NO_RECORD_AFTER_DECISION.value


class TestLimitEqualityBoundaries:
    """LIMIT orders at exactly the executable price fill (equality is not
    treated as a miss on either side)."""

    def test_limit_buy_at_exact_ask_fills(self) -> None:
        records = (
            tick(utc(2026, 1, 1, 9, 0), "100", "99.5", "100.5"),
            tick(utc(2026, 1, 1, 9, 1), "100", "99.5", "100.5"),
        )
        result = run(
            records,
            order(IntentSide.BUY, IntentType.LIMIT, utc(2026, 1, 1, 9, 0, 30), limit_price="100.5"),
        )
        (fill,) = result.fills
        assert fill.fill_price == Decimal("100.5")

    def test_limit_sell_at_exact_bid_fills(self) -> None:
        records = (
            tick(utc(2026, 1, 1, 9, 0), "100", "99.5", "100.5"),
            tick(utc(2026, 1, 1, 9, 1), "100", "99.5", "100.5"),
            tick(utc(2026, 1, 1, 9, 2), "100", "99.5", "100.5"),
        )
        result = run(
            records,
            order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 20)),
            order(IntentSide.SELL, IntentType.LIMIT, utc(2026, 1, 1, 9, 1, 30), limit_price="99.5"),
        )
        (sell_fill,) = [f for f in result.fills if f.side is IntentSide.SELL]
        assert sell_fill.fill_price == Decimal("99.5")

    def test_candle_limit_at_exact_open_fills(self) -> None:
        records = (
            candle(utc(2026, 1, 1, 9, 0), "100", "105", "99", "104"),
            candle(utc(2026, 1, 1, 9, 1), "101", "106", "100", "105"),
        )
        result = run(
            records,
            order(IntentSide.BUY, IntentType.LIMIT, utc(2026, 1, 1, 9, 0, 30), limit_price="101"),
        )
        (fill,) = result.fills
        assert fill.fill_price == Decimal("101")


class TestDuplicateAnchorSequencing:
    """Two intents anchored at the SAME record execute in intent order:
    the SELL at the shared anchor observes the cash and position produced by
    the BUY at that same record."""

    def test_buy_then_sell_at_same_anchor_record(self) -> None:
        records = (
            tick(utc(2026, 1, 1, 9, 0), "100", "99.5", "100.5"),
            tick(utc(2026, 1, 1, 9, 1), "100", "99.5", "100.5"),
            tick(utc(2026, 1, 1, 9, 2), "100", "99.5", "100.5"),
        )
        result = run(
            records,
            order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 20)),
            order(IntentSide.SELL, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 40)),
        )
        assert len(result.outcomes) == 2
        assert [o.filled for o in result.outcomes] == [True, True]
        # Both fills anchored at the second record (first strictly after 09:00:40).
        assert result.fills[0].record_index == 1
        assert result.fills[1].record_index == 1
        # Round trip across the spread: BUY @ask 100.5, SELL @bid 99.5 — the
        # 10-share spread cost (10 x 1.0) is real; final equity is 99990.
        assert result.final_equity == Decimal("99990")

    def test_second_intent_rejected_when_same_anchor_cash_insufficient(self) -> None:
        # Capital 2000, commission 0: BUY 10 @100.5 costs 1005 (cash 995); the
        # second BUY at the same anchor costs another 1005 > 995 -> rejected,
        # observing the cash state produced by the first intent.
        result = run_backtest(
            inputs=make_input(
                (
                    tick(utc(2026, 1, 1, 9, 0), "100", "99.5", "100.5"),
                    tick(utc(2026, 1, 1, 9, 1), "100", "99.5", "100.5"),
                )
            ),
            intents=(
                order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 20)),
                order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 40)),
            ),
            cost_model=CostModel(commission_per_fill=Decimal("0"), slippage_bps=Decimal("0")),
            initial_capital=Decimal("2000"),
        )
        assert [o.filled for o in result.outcomes] == [True, False]
        assert result.outcomes[1].reason == UnfilledReason.INSUFFICIENT_CASH.value


class TestNonPositiveAnchorRejection:
    """A non-positive anchor (smuggled via pydantic model_construct-style
    bypass) must be rejected loudly, never silently "filled" at 0 or less."""

    def _bypass_input_validation(records: tuple) -> BacktestInput:
        # The foundation BacktestInput.__post_init__ re-validates records
        # (bid<=ask, ascending, etc.). The smuggling path for a dataclass is
        # object.__new__ + object.__setattr__ — construct the input without
        # running validation so the engine's own guards are what reject it.
        input_obj = object.__new__(BacktestInput)
        object.__setattr__(input_obj, "dataset_id", "ds")
        object.__setattr__(input_obj, "source", "unit")
        object.__setattr__(input_obj, "records", records)
        object.__setattr__(input_obj, "metadata", {})
        return input_obj

    def test_zero_ask_rejected(self) -> None:
        # Pydantic refuses to construct ask=0, so the smuggling path is
        # model_construct on the tick plus __new__-bypass on the input (the
        # exact bypass class the safety review named). The engine must still
        # reject the non-positive anchor loudly.
        smuggled_tick = MarketTick.model_construct(
            instrument_id=INSTRUMENT,
            exchange="NSE",
            symbol="TEST",
            timestamp=utc(2026, 1, 1, 9, 1),
            ltp=Decimal("100"),
            volume=Decimal("0"),
            bid=Decimal("99.5"),
            ask=Decimal("0"),
            bid_quantity=Decimal("0"),
            ask_quantity=Decimal("0"),
            source_broker="unit",
            source_sequence="seq-zero-ask",
            received_at=utc(2026, 1, 1, 9, 1),
        )
        records = (
            tick(utc(2026, 1, 1, 9, 0), "100", "99.5", "100.5"),
            smuggled_tick,
        )
        try:
            run_backtest(
                inputs=TestNonPositiveAnchorRejection._bypass_input_validation(records),
                intents=(
                    order(IntentSide.BUY, IntentType.LIMIT, utc(2026, 1, 1, 9, 0, 30), limit_price="100"),
                ),
                cost_model=CostModel(commission_per_fill=Decimal("0"), slippage_bps=Decimal("0")),
                initial_capital=Decimal("100000"),
            )
        except Exception as exc:  # BacktestEngineError surfaced through run_backtest
            assert "anchor price" in str(exc)
        else:
            raise AssertionError("non-positive ask must be rejected")

    def test_negative_bid_rejected(self) -> None:
        smuggled_tick = MarketTick.model_construct(
            instrument_id=INSTRUMENT,
            exchange="NSE",
            symbol="TEST",
            timestamp=utc(2026, 1, 1, 9, 2),
            ltp=Decimal("100"),
            volume=Decimal("0"),
            bid=Decimal("-10"),
            ask=Decimal("100.5"),
            bid_quantity=Decimal("0"),
            ask_quantity=Decimal("0"),
            source_broker="unit",
            source_sequence="seq-neg-bid",
            received_at=utc(2026, 1, 1, 9, 2),
        )
        records = (
            tick(utc(2026, 1, 1, 9, 0), "100", "99.5", "100.5"),
            tick(utc(2026, 1, 1, 9, 1), "100", "99.5", "100.5"),
            smuggled_tick,
        )
        try:
            run_backtest(
                inputs=TestNonPositiveAnchorRejection._bypass_input_validation(records),
                intents=(
                    order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 20)),
                    order(IntentSide.SELL, IntentType.MARKET, utc(2026, 1, 1, 9, 1, 30)),
                ),
                cost_model=CostModel(commission_per_fill=Decimal("0"), slippage_bps=Decimal("0")),
                initial_capital=Decimal("100000"),
            )
        except Exception as exc:
            assert "anchor price" in str(exc)
        else:
            raise AssertionError("negative bid must be rejected")

    def test_zero_candle_open_rejected(self) -> None:
        smuggled_candle = MarketCandle.model_construct(
            instrument_id=INSTRUMENT,
            exchange="NSE",
            symbol="TEST",
            timeframe=CandleTimeframe.ONE_MINUTE,
            candle_start=utc(2026, 1, 1, 9, 1),
            open_price=Decimal("0"),
            high_price=Decimal("105"),
            low_price=Decimal("99"),
            close_price=Decimal("104"),
            source_broker="unit",
            generated_at=utc(2026, 1, 1, 9, 1),
        )
        records = (
            candle(utc(2026, 1, 1, 9, 0), "100", "105", "99", "104"),
            smuggled_candle,
        )
        try:
            run(records, order(IntentSide.BUY, IntentType.LIMIT, utc(2026, 1, 1, 9, 0, 30), limit_price="100"))
        except Exception as exc:
            assert "anchor price" in str(exc)
        else:
            raise AssertionError("non-positive candle open must be rejected")
