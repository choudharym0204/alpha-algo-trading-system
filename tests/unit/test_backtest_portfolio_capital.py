from __future__ import annotations

from decimal import Decimal

import pytest

from alpha_algo_backtest_portfolio import CapitalAllocation, PortfolioBacktestError


class TestCapitalAllocation:
    def test_defaults(self) -> None:
        alloc = CapitalAllocation(initial_capital=Decimal("10000"))
        assert alloc.reserved_cash == Decimal("0")
        assert alloc.per_symbol_budget == ()

    def test_reserved_cash_within_capital(self) -> None:
        alloc = CapitalAllocation(initial_capital=Decimal("10000"), reserved_cash=Decimal("2000"))
        assert alloc.reserved_cash == Decimal("2000")

    def test_reserved_cash_exceeding_capital_rejected(self) -> None:
        with pytest.raises(PortfolioBacktestError):
            CapitalAllocation(initial_capital=Decimal("1000"), reserved_cash=Decimal("2000"))

    def test_negative_capital_rejected(self) -> None:
        with pytest.raises(PortfolioBacktestError):
            CapitalAllocation(initial_capital=Decimal("0"))

    def test_negative_reserved_rejected(self) -> None:
        with pytest.raises(PortfolioBacktestError):
            CapitalAllocation(initial_capital=Decimal("1000"), reserved_cash=Decimal("-1"))

    def test_budget_lookup(self) -> None:
        alloc = CapitalAllocation(
            initial_capital=Decimal("10000"),
            per_symbol_budget=(("A", Decimal("500")), ("B", Decimal("300"))),
        )
        assert alloc.budget_for("A") == Decimal("500")
        assert alloc.budget_for("C") is None

    def test_duplicate_budget_symbol_rejected(self) -> None:
        with pytest.raises(PortfolioBacktestError):
            CapitalAllocation(
                initial_capital=Decimal("10000"),
                per_symbol_budget=(("A", Decimal("500")), ("A", Decimal("300"))),
            )

    def test_nonpositive_budget_rejected(self) -> None:
        with pytest.raises(PortfolioBacktestError):
            CapitalAllocation(
                initial_capital=Decimal("10000"),
                per_symbol_budget=(("A", Decimal("0")),),
            )
