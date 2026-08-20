from __future__ import annotations

from datetime import timedelta

import pytest

from alpha_algo_backtest_engine import IntentSide, IntentType
from alpha_algo_backtest_latency import LatencyError, LatencyModel, apply_latency, apply_latency_to_intent
from tests.unit.backtest_p16_test_support import order, utc


class TestLatencyModel:
    def test_default_is_zero(self) -> None:
        model = LatencyModel()
        assert model.total_latency == timedelta(0)
        assert model.is_zero

    def test_components_sum(self) -> None:
        model = LatencyModel(
            signal_latency=timedelta(seconds=1),
            decision_latency=timedelta(seconds=2),
            submission_latency=timedelta(seconds=3),
            fill_latency=timedelta(seconds=4),
        )
        assert model.total_latency == timedelta(seconds=10)

    def test_negative_latency_rejected(self) -> None:
        with pytest.raises(LatencyError):
            LatencyModel(signal_latency=timedelta(seconds=-1))

    def test_zero_latency_identity(self) -> None:
        intent = order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 30))
        shifted = apply_latency_to_intent(intent, LatencyModel())
        assert shifted == intent

    def test_fixed_latency_shifts_decided_at(self) -> None:
        intent = order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 30))
        shifted = apply_latency_to_intent(intent, LatencyModel(submission_latency=timedelta(seconds=5)))
        assert shifted.decided_at == utc(2026, 1, 1, 9, 0, 35)

    def test_apply_latency_preserves_other_fields(self) -> None:
        intent = order(IntentSide.SELL, IntentType.LIMIT, utc(2026, 1, 1, 9, 0, 30), quantity="7", limit_price="105")
        shifted = apply_latency_to_intent(intent, LatencyModel(decision_latency=timedelta(seconds=1)))
        assert shifted.side is IntentSide.SELL
        assert shifted.order_type is IntentType.LIMIT
        assert shifted.quantity == intent.quantity
        assert shifted.limit_price == intent.limit_price

    def test_apply_latency_many(self) -> None:
        intents = (
            order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 30)),
            order(IntentSide.SELL, IntentType.MARKET, utc(2026, 1, 1, 9, 1, 0)),
        )
        shifted = apply_latency(intents, LatencyModel(submission_latency=timedelta(seconds=5)))
        assert shifted[0].decided_at == utc(2026, 1, 1, 9, 0, 35)
        assert shifted[1].decided_at == utc(2026, 1, 1, 9, 1, 5)

    def test_invalid_intent_rejected(self) -> None:
        with pytest.raises(LatencyError):
            apply_latency_to_intent("not-an-intent", LatencyModel())  # type: ignore[arg-type]

    def test_deterministic(self) -> None:
        intent = order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 30))
        model = LatencyModel(fill_latency=timedelta(milliseconds=250))
        assert apply_latency_to_intent(intent, model) == apply_latency_to_intent(intent, model)


class TestLatencyAffectsFillTiming:
    def test_latency_moves_fill_to_later_record(self) -> None:
        from alpha_algo_backtest_engine import run_backtest
        from alpha_algo_backtesting import BacktestInput
        from tests.unit.backtest_p16_test_support import make_input, tick, zero_cost
        from decimal import Decimal

        records = (
            tick(utc(2026, 1, 1, 9, 0), "100"),
            tick(utc(2026, 1, 1, 9, 1), "110"),
            tick(utc(2026, 1, 1, 9, 2), "120"),
        )
        inputs = make_input("ds", records)
        raw_intent = order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 30))

        no_latency = run_backtest(
            inputs=inputs, intents=(raw_intent,), cost_model=zero_cost(), initial_capital=Decimal("10000")
        )
        # Fills at 9:01 (first record strictly after 9:00:30) at price 110.
        assert no_latency.fills[0].anchor_price == Decimal("110")

        delayed = apply_latency_to_intent(raw_intent, LatencyModel(submission_latency=timedelta(seconds=30)))
        # decided_at -> 9:01:00, so first record strictly after is 9:02 at 120.
        with_latency = run_backtest(
            inputs=inputs, intents=(delayed,), cost_model=zero_cost(), initial_capital=Decimal("10000")
        )
        assert with_latency.fills[0].anchor_price == Decimal("120")
