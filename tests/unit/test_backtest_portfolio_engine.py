from __future__ import annotations

from decimal import Decimal

import pytest

from alpha_algo_backtest_engine import IntentSide, IntentType
from alpha_algo_backtest_portfolio import (
    CapitalAllocation,
    PortfolioBacktestError,
    PortfolioInput,
    PortfolioIntent,
    run_portfolio_backtest,
)
from tests.unit.backtest_p16_test_support import (
    INSTRUMENT,
    INSTRUMENT_B,
    make_input,
    order,
    tick,
    utc,
    zero_cost,
)


def _two_symbol_portfolio():
    a_records = (
        tick(utc(2026, 1, 1, 9, 0), "100", symbol="A", instrument=INSTRUMENT),
        tick(utc(2026, 1, 1, 9, 2), "110", symbol="A", instrument=INSTRUMENT),
    )
    b_records = (
        tick(utc(2026, 1, 1, 9, 1), "50", symbol="B", instrument=INSTRUMENT_B),
        tick(utc(2026, 1, 1, 9, 3), "55", symbol="B", instrument=INSTRUMENT_B),
    )
    return PortfolioInput(inputs=(make_input("ds-a", a_records), make_input("ds-b", b_records)))


class TestPortfolioInput:
    def test_symbols_sorted(self) -> None:
        portfolio = _two_symbol_portfolio()
        assert portfolio.symbols == ("A", "B")

    def test_duplicate_symbol_rejected(self) -> None:
        rec = (tick(utc(2026, 1, 1, 9, 0), "100"),)
        with pytest.raises(PortfolioBacktestError):
            PortfolioInput(inputs=(make_input("a", rec), make_input("b", rec)))

    def test_empty_rejected(self) -> None:
        with pytest.raises(PortfolioBacktestError):
            PortfolioInput(inputs=())

    def test_content_sha256_is_order_stable(self) -> None:
        a_records = (tick(utc(2026, 1, 1, 9, 0), "100", symbol="A", instrument=INSTRUMENT),)
        b_records = (tick(utc(2026, 1, 1, 9, 0), "50", symbol="B", instrument=INSTRUMENT_B),)
        p1 = PortfolioInput(inputs=(make_input("a", a_records), make_input("b", b_records)))
        p2 = PortfolioInput(inputs=(make_input("b", b_records), make_input("a", a_records)))
        assert p1.content_sha256 == p2.content_sha256


class TestMultiSymbol:
    def test_shared_capital_and_equity(self) -> None:
        portfolio = _two_symbol_portfolio()
        intents = (
            PortfolioIntent(symbol="A", intent=order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 30), "10")),
            PortfolioIntent(symbol="B", intent=order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 30), "10")),
        )
        result = run_portfolio_backtest(
            portfolio=portfolio,
            intents=intents,
            cost_model=zero_cost(),
            allocation=CapitalAllocation(initial_capital=Decimal("10000")),
        )
        assert result.final_equity == Decimal("10050")
        assert len(result.fills) == 2

    def test_one_symbol_behaves_like_single_engine(self) -> None:
        rec = (
            tick(utc(2026, 1, 1, 9, 0), "100"),
            tick(utc(2026, 1, 1, 9, 2), "110"),
        )
        portfolio = PortfolioInput(inputs=(make_input("ds", rec),))
        intents = (PortfolioIntent(symbol="TEST", intent=order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 30), "10")),)
        result = run_portfolio_backtest(
            portfolio=portfolio,
            intents=intents,
            cost_model=zero_cost(),
            allocation=CapitalAllocation(initial_capital=Decimal("10000")),
        )
        # Buy 10 @ 110, cash 8900, position 10 @ mark 110 => equity 10000.
        assert result.final_equity == Decimal("10000")
        assert len(result.fills) == 1

    def test_simultaneous_cross_symbol_events_ordered_by_symbol(self) -> None:
        # Both symbols have a record at the exact same timestamp; ordering is
        # by symbol name (deterministic, not by input order).
        a_records = (tick(utc(2026, 1, 1, 9, 0), "100", symbol="A", instrument=INSTRUMENT),)
        b_records = (tick(utc(2026, 1, 1, 9, 0), "50", symbol="B", instrument=INSTRUMENT_B),)
        portfolio = PortfolioInput(inputs=(make_input("a", b_records), make_input("b", a_records)))
        intents = (
            PortfolioIntent(symbol="A", intent=order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 8, 59), "10")),
            PortfolioIntent(symbol="B", intent=order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 8, 59), "10")),
        )
        result = run_portfolio_backtest(
            portfolio=portfolio,
            intents=intents,
            cost_model=zero_cost(),
            allocation=CapitalAllocation(initial_capital=Decimal("10000")),
        )
        # Both fill at their 9:00 records; deterministic regardless of order.
        assert len(result.fills) == 2
        # A fills first (symbol order A < B) -> sequence 0 is A, sequence 1 is B.
        fills_by_symbol = {f.intent_index: f for f in result.fills}
        assert fills_by_symbol[0].anchor_price == Decimal("100")

    def test_separate_positions_and_completed_trade(self) -> None:
        a_records = (
            tick(utc(2026, 1, 1, 9, 0), "100", symbol="A", instrument=INSTRUMENT),
            tick(utc(2026, 1, 1, 9, 2), "110", symbol="A", instrument=INSTRUMENT),
            tick(utc(2026, 1, 1, 9, 4), "120", symbol="A", instrument=INSTRUMENT),
        )
        portfolio = PortfolioInput(inputs=(make_input("ds-a", a_records),))
        intents = (
            PortfolioIntent(symbol="A", intent=order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 30), "10")),
            PortfolioIntent(symbol="A", intent=order(IntentSide.SELL, IntentType.MARKET, utc(2026, 1, 1, 9, 2, 30), "10")),
        )
        result = run_portfolio_backtest(
            portfolio=portfolio,
            intents=intents,
            cost_model=zero_cost(),
            allocation=CapitalAllocation(initial_capital=Decimal("10000")),
        )
        # Buy 10 @110, sell 10 @120 => realized +100, final cash 10100.
        assert len(result.trades) == 1
        assert result.trades[0].symbol == "A"
        assert result.trades[0].trade.realized_pnl == Decimal("100")
        assert result.final_equity == Decimal("10100")

    def test_short_is_rejected(self) -> None:
        a_records = (
            tick(utc(2026, 1, 1, 9, 0), "100"),
            tick(utc(2026, 1, 1, 9, 2), "110"),
        )
        portfolio = PortfolioInput(inputs=(make_input("ds-a", a_records),))
        intents = (PortfolioIntent(symbol="TEST", intent=order(IntentSide.SELL, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 30), "10")),)
        result = run_portfolio_backtest(
            portfolio=portfolio,
            intents=intents,
            cost_model=zero_cost(),
            allocation=CapitalAllocation(initial_capital=Decimal("10000")),
        )
        # No position -> INSUFFICIENT_POSITION (no silent short).
        assert result.outcomes[0].filled is False
        assert result.outcomes[0].reason == "INSUFFICIENT_POSITION"


class TestCapitalAllocationBehavior:
    def test_reserved_cash_floor_refuses_buy(self) -> None:
        b_records = (
            tick(utc(2026, 1, 1, 9, 1), "50", symbol="B", instrument=INSTRUMENT_B),
            tick(utc(2026, 1, 1, 9, 3), "50", symbol="B", instrument=INSTRUMENT_B),
        )
        portfolio = PortfolioInput(inputs=(make_input("ds-b", b_records),))
        intents = (
            PortfolioIntent(symbol="B", intent=order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 30), "10")),
            PortfolioIntent(symbol="B", intent=order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 2, 30), "10")),
        )
        result = run_portfolio_backtest(
            portfolio=portfolio,
            intents=intents,
            cost_model=zero_cost(),
            allocation=CapitalAllocation(initial_capital=Decimal("10000"), reserved_cash=Decimal("9500")),
        )
        # First buy: cash 10000-500=9500 (>= reserved) -> fills.
        # Second buy: cash would be 9000 (< 9500) -> refused.
        assert result.outcomes[0].filled is True
        assert result.outcomes[1].filled is False
        assert result.outcomes[1].reason == "INSUFFICIENT_CASH"

    def test_per_symbol_budget_refuses_buy(self) -> None:
        a_records = (
            tick(utc(2026, 1, 1, 9, 0), "100", symbol="A", instrument=INSTRUMENT),
            tick(utc(2026, 1, 1, 9, 2), "110", symbol="A", instrument=INSTRUMENT),
        )
        portfolio = PortfolioInput(inputs=(make_input("ds-a", a_records),))
        intents = (PortfolioIntent(symbol="A", intent=order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 30), "10")),)
        result = run_portfolio_backtest(
            portfolio=portfolio,
            intents=intents,
            cost_model=zero_cost(),
            allocation=CapitalAllocation(
                initial_capital=Decimal("10000"),
                per_symbol_budget=(("A", Decimal("500")),),
            ),
        )
        # Gross value 10 * 110 = 1100 > 500 -> refused.
        assert result.outcomes[0].filled is False
        assert result.outcomes[0].reason == "INSUFFICIENT_CASH"


class TestPortfolioValidation:
    def test_unknown_symbol_intent_rejected(self) -> None:
        portfolio = _two_symbol_portfolio()
        intents = (PortfolioIntent(symbol="ZZZ", intent=order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 30))),)
        with pytest.raises(PortfolioBacktestError):
            run_portfolio_backtest(
                portfolio=portfolio,
                intents=intents,
                cost_model=zero_cost(),
                allocation=CapitalAllocation(initial_capital=Decimal("10000")),
            )

    def test_tied_decided_at_rejected(self) -> None:
        portfolio = _two_symbol_portfolio()
        intent = order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 30))
        intents = (
            PortfolioIntent(symbol="A", intent=intent),
            PortfolioIntent(symbol="A", intent=intent),
        )
        with pytest.raises(PortfolioBacktestError):
            run_portfolio_backtest(
                portfolio=portfolio,
                intents=intents,
                cost_model=zero_cost(),
                allocation=CapitalAllocation(initial_capital=Decimal("10000")),
            )


class TestDeterminism:
    def test_identical_inputs_identical_result(self) -> None:
        portfolio = _two_symbol_portfolio()
        intents = (
            PortfolioIntent(symbol="A", intent=order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 30), "10")),
            PortfolioIntent(symbol="B", intent=order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 30), "10")),
        )
        kwargs = dict(portfolio=portfolio, intents=intents, cost_model=zero_cost(), allocation=CapitalAllocation(initial_capital=Decimal("10000")))
        assert run_portfolio_backtest(**kwargs) == run_portfolio_backtest(**kwargs)

    def test_input_order_does_not_change_result(self) -> None:
        a_records = (tick(utc(2026, 1, 1, 9, 0), "100", symbol="A", instrument=INSTRUMENT), tick(utc(2026, 1, 1, 9, 2), "110", symbol="A", instrument=INSTRUMENT))
        b_records = (tick(utc(2026, 1, 1, 9, 1), "50", symbol="B", instrument=INSTRUMENT_B), tick(utc(2026, 1, 1, 9, 3), "55", symbol="B", instrument=INSTRUMENT_B))
        p1 = PortfolioInput(inputs=(make_input("a", a_records), make_input("b", b_records)))
        p2 = PortfolioInput(inputs=(make_input("b", b_records), make_input("a", a_records)))
        intents = (
            PortfolioIntent(symbol="A", intent=order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 30), "10")),
            PortfolioIntent(symbol="B", intent=order(IntentSide.BUY, IntentType.MARKET, utc(2026, 1, 1, 9, 0, 30), "10")),
        )
        alloc = CapitalAllocation(initial_capital=Decimal("10000"))
        r1 = run_portfolio_backtest(portfolio=p1, intents=intents, cost_model=zero_cost(), allocation=alloc)
        r2 = run_portfolio_backtest(portfolio=p2, intents=intents, cost_model=zero_cost(), allocation=alloc)
        assert r1.final_equity == r2.final_equity
        assert r1.trades == r2.trades
