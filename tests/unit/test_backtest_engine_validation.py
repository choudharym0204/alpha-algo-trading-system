from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from alpha_algo_backtest_engine import (
    BacktestEngineError,
    CostModel,
    IntentSide,
    IntentType,
    OrderIntent,
    run_backtest,
)
from alpha_algo_backtesting import BacktestInput

INSTRUMENT = UUID("00000000-0000-0000-0000-000000000001")


def utc(y: int, mo: int, d: int, h: int = 9, mi: int = 0, s: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, s, tzinfo=timezone.utc)


def intent(
    side: IntentSide,
    order_type: IntentType,
    quantity: str = "10",
    decided_at: datetime | None = None,
    limit_price: str | None = None,
) -> OrderIntent:
    return OrderIntent(
        side=side,
        order_type=order_type,
        quantity=Decimal(quantity),
        decided_at=decided_at or utc(2026, 1, 1, 9, 0, 30),
        limit_price=Decimal(limit_price) if limit_price is not None else None,
    )


def make_input(records: tuple) -> BacktestInput:
    return BacktestInput(dataset_id="ds", source="unit", records=records)


class TestIntentConstruction:
    def test_valid_market_intent(self) -> None:
        item = intent(IntentSide.BUY, IntentType.MARKET)
        assert item.quantity == Decimal("10")
        assert item.limit_price is None

    def test_valid_limit_intent(self) -> None:
        item = intent(IntentSide.BUY, IntentType.LIMIT, limit_price="100")
        assert item.limit_price == Decimal("100")

    def test_quantity_must_be_positive(self) -> None:
        with pytest.raises(BacktestEngineError):
            intent(IntentSide.BUY, IntentType.MARKET, quantity="0")
        with pytest.raises(BacktestEngineError):
            intent(IntentSide.BUY, IntentType.MARKET, quantity="-5")

    def test_quantity_must_be_decimal(self) -> None:
        with pytest.raises(BacktestEngineError):
            OrderIntent(
                side=IntentSide.BUY,
                order_type=IntentType.MARKET,
                quantity=5,  # type: ignore[arg-type]
                decided_at=utc(2026, 1, 1),
            )
        with pytest.raises(BacktestEngineError):
            OrderIntent(
                side=IntentSide.BUY,
                order_type=IntentType.MARKET,
                quantity=5.5,  # type: ignore[arg-type]
                decided_at=utc(2026, 1, 1),
            )
        with pytest.raises(BacktestEngineError):
            OrderIntent(
                side=IntentSide.BUY,
                order_type=IntentType.MARKET,
                quantity="10",  # type: ignore[arg-type]
                decided_at=utc(2026, 1, 1),
            )

    def test_quantity_must_be_finite(self) -> None:
        with pytest.raises(BacktestEngineError):
            intent(IntentSide.BUY, IntentType.MARKET, quantity="Infinity")
        with pytest.raises(BacktestEngineError):
            intent(IntentSide.BUY, IntentType.MARKET, quantity="NaN")

    def test_decided_at_must_be_timezone_aware(self) -> None:
        with pytest.raises(BacktestEngineError):
            OrderIntent(
                side=IntentSide.BUY,
                order_type=IntentType.MARKET,
                quantity=Decimal("10"),
                decided_at=datetime(2026, 1, 1, 9, 0, 30),
            )

    def test_limit_requires_limit_price(self) -> None:
        with pytest.raises(BacktestEngineError):
            intent(IntentSide.BUY, IntentType.LIMIT)

    def test_limit_price_must_be_positive_and_finite(self) -> None:
        with pytest.raises(BacktestEngineError):
            intent(IntentSide.BUY, IntentType.LIMIT, limit_price="0")
        with pytest.raises(BacktestEngineError):
            intent(IntentSide.BUY, IntentType.LIMIT, limit_price="-1")
        with pytest.raises(BacktestEngineError):
            intent(IntentSide.BUY, IntentType.LIMIT, limit_price="Infinity")

    def test_market_must_not_carry_limit_price(self) -> None:
        with pytest.raises(BacktestEngineError):
            intent(IntentSide.BUY, IntentType.MARKET, limit_price="100")

    def test_sides_and_types_are_exactly_the_v1_members(self) -> None:
        assert [member.value for member in IntentSide] == ["BUY", "SELL"]
        assert [member.value for member in IntentType] == ["MARKET", "LIMIT"]

    def test_intent_is_frozen(self) -> None:
        item = intent(IntentSide.BUY, IntentType.MARKET)
        with pytest.raises(Exception):
            item.quantity = Decimal("20")  # type: ignore[misc]


class TestCostModelConstruction:
    def test_valid_cost_model(self) -> None:
        model = CostModel(commission_per_fill=Decimal("5"), slippage_bps=Decimal("10"))
        assert model.commission_per_fill == Decimal("5")

    def test_explicit_zero_cost_is_valid(self) -> None:
        model = CostModel(commission_per_fill=Decimal("0"), slippage_bps=Decimal("0"))
        assert model.commission_per_fill == Decimal("0")

    def test_no_defaults(self) -> None:
        with pytest.raises(TypeError):
            CostModel()  # type: ignore[call-arg]

    def test_negative_commission_rejected(self) -> None:
        with pytest.raises(BacktestEngineError):
            CostModel(commission_per_fill=Decimal("-1"), slippage_bps=Decimal("0"))

    def test_negative_slippage_rejected(self) -> None:
        with pytest.raises(BacktestEngineError):
            CostModel(commission_per_fill=Decimal("0"), slippage_bps=Decimal("-1"))

    def test_slippage_at_or_above_10000_bps_rejected(self) -> None:
        with pytest.raises(BacktestEngineError):
            CostModel(commission_per_fill=Decimal("0"), slippage_bps=Decimal("10000"))
        with pytest.raises(BacktestEngineError):
            CostModel(commission_per_fill=Decimal("0"), slippage_bps=Decimal("15000"))

    def test_non_decimal_rejected(self) -> None:
        with pytest.raises(BacktestEngineError):
            CostModel(commission_per_fill=5, slippage_bps=Decimal("0"))  # type: ignore[arg-type]
        with pytest.raises(BacktestEngineError):
            CostModel(commission_per_fill=Decimal("0"), slippage_bps=10.5)  # type: ignore[arg-type]
        with pytest.raises(BacktestEngineError):
            CostModel(commission_per_fill=Decimal("0"), slippage_bps="10")  # type: ignore[arg-type]

    def test_non_finite_rejected(self) -> None:
        with pytest.raises(BacktestEngineError):
            CostModel(commission_per_fill=Decimal("Infinity"), slippage_bps=Decimal("0"))
        with pytest.raises(BacktestEngineError):
            CostModel(commission_per_fill=Decimal("0"), slippage_bps=Decimal("NaN"))


class TestRunEntryValidation:
    def test_inputs_must_be_backtest_input(self) -> None:
        with pytest.raises(BacktestEngineError):
            run_backtest(
                inputs="not-an-input",  # type: ignore[arg-type]
                intents=(),
                cost_model=CostModel(Decimal("0"), Decimal("0")),
                initial_capital=Decimal("100000"),
            )

    def test_intents_must_be_tuple_of_order_intent(self) -> None:
        from alpha_algo_contracts import MarketTick

        tick = MarketTick(
            instrument_id=INSTRUMENT,
            exchange="NSE",
            symbol="TEST",
            timestamp=utc(2026, 1, 1, 9, 0),
            ltp=Decimal("100"),
            source_broker="unit",
            source_sequence="1",
            received_at=utc(2026, 1, 1, 9, 0),
        )
        with pytest.raises(BacktestEngineError):
            run_backtest(
                inputs=make_input((tick,)),
                intents=(intent(IntentSide.BUY, IntentType.MARKET), "nope"),  # type: ignore[arg-type]
                cost_model=CostModel(Decimal("0"), Decimal("0")),
                initial_capital=Decimal("100000"),
            )

    def test_initial_capital_must_be_positive_finite_decimal(self) -> None:
        from alpha_algo_contracts import MarketTick

        tick = MarketTick(
            instrument_id=INSTRUMENT,
            exchange="NSE",
            symbol="TEST",
            timestamp=utc(2026, 1, 1, 9, 0),
            ltp=Decimal("100"),
            source_broker="unit",
            source_sequence="1",
            received_at=utc(2026, 1, 1, 9, 0),
        )
        for bad in (Decimal("0"), Decimal("-1"), Decimal("Infinity"), 100000, "100000"):
            with pytest.raises(BacktestEngineError):
                run_backtest(
                    inputs=make_input((tick,)),
                    intents=(),
                    cost_model=CostModel(Decimal("0"), Decimal("0")),
                    initial_capital=bad,  # type: ignore[arg-type]
                )

    def test_cost_model_must_be_cost_model(self) -> None:
        from alpha_algo_contracts import MarketTick

        tick = MarketTick(
            instrument_id=INSTRUMENT,
            exchange="NSE",
            symbol="TEST",
            timestamp=utc(2026, 1, 1, 9, 0),
            ltp=Decimal("100"),
            source_broker="unit",
            source_sequence="1",
            received_at=utc(2026, 1, 1, 9, 0),
        )
        with pytest.raises(BacktestEngineError):
            run_backtest(
                inputs=make_input((tick,)),
                intents=(),
                cost_model="model",  # type: ignore[arg-type]
                initial_capital=Decimal("100000"),
            )

    def test_unsorted_intents_rejected_never_reordered(self) -> None:
        from alpha_algo_contracts import MarketTick

        tick = MarketTick(
            instrument_id=INSTRUMENT,
            exchange="NSE",
            symbol="TEST",
            timestamp=utc(2026, 1, 1, 9, 0),
            ltp=Decimal("100"),
            source_broker="unit",
            source_sequence="1",
            received_at=utc(2026, 1, 1, 9, 0),
        )
        later = intent(IntentSide.BUY, IntentType.MARKET, decided_at=utc(2026, 1, 1, 9, 0, 40))
        earlier = intent(IntentSide.BUY, IntentType.MARKET, decided_at=utc(2026, 1, 1, 9, 0, 20))
        with pytest.raises(BacktestEngineError):
            run_backtest(
                inputs=make_input((tick,)),
                intents=(later, earlier),
                cost_model=CostModel(Decimal("0"), Decimal("0")),
                initial_capital=Decimal("100000"),
            )

    def test_tied_decided_at_rejected(self) -> None:
        from alpha_algo_contracts import MarketTick

        tick = MarketTick(
            instrument_id=INSTRUMENT,
            exchange="NSE",
            symbol="TEST",
            timestamp=utc(2026, 1, 1, 9, 0),
            ltp=Decimal("100"),
            source_broker="unit",
            source_sequence="1",
            received_at=utc(2026, 1, 1, 9, 0),
        )
        same = intent(IntentSide.BUY, IntentType.MARKET, decided_at=utc(2026, 1, 1, 9, 0, 20))
        with pytest.raises(BacktestEngineError):
            run_backtest(
                inputs=make_input((tick,)),
                intents=(same, same),
                cost_model=CostModel(Decimal("0"), Decimal("0")),
                initial_capital=Decimal("100000"),
            )

    def test_backtest_run_mode_is_pinned_to_backtest(self) -> None:
        from alpha_algo_backtesting import BacktestTradingMode

        assert [member.value for member in BacktestTradingMode] == ["BACKTEST"]
