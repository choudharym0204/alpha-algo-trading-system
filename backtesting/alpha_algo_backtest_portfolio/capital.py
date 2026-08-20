"""Explicit capital allocation for the multi-symbol portfolio sim (P16).

The allocation model is a **shared cash pool with a reserved-cash floor and
optional per-symbol budget caps**:

- ``initial_capital`` is the total simulated capital (never infinite — every
  BUY is evaluated against available cash).
- ``reserved_cash`` is held back and never spent; the spendable floor is
  ``cash >= reserved_cash`` at all times (the simulator refuses any fill that
  would dip below it).
- ``per_symbol_budget`` (optional) caps the total gross notional a single
  symbol may carry; a BUY that would push a symbol's gross notional over its
  budget is refused.

There is no margin and no leverage in v1: cash never goes negative and
reserved cash is never breached. The model is long-only, matching the engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from alpha_algo_backtest_portfolio.errors import PortfolioBacktestError

__all__ = ["CAPITAL_ALLOCATION_POLICY", "CapitalAllocation"]

CAPITAL_ALLOCATION_POLICY = (
    "Shared cash pool with a reserved-cash floor (cash never below reserved) "
    "and optional per-symbol budget caps (gross notional per symbol). No "
    "margin, no leverage, no infinite capital. Long-only. Every BUY is "
    "evaluated against available cash and any per-symbol budget."
)


@dataclass(frozen=True)
class CapitalAllocation:
    """Explicit capital-allocation parameters for a portfolio run."""

    initial_capital: Decimal
    reserved_cash: Decimal = Decimal("0")
    per_symbol_budget: tuple[tuple[str, Decimal], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.initial_capital, Decimal) or not self.initial_capital.is_finite() or self.initial_capital <= 0:
            raise PortfolioBacktestError("initial_capital must be a positive finite Decimal")
        if not isinstance(self.reserved_cash, Decimal) or not self.reserved_cash.is_finite() or self.reserved_cash < 0:
            raise PortfolioBacktestError("reserved_cash must be a non-negative finite Decimal")
        if self.reserved_cash > self.initial_capital:
            raise PortfolioBacktestError("reserved_cash must not exceed initial_capital")
        if not isinstance(self.per_symbol_budget, tuple):
            raise PortfolioBacktestError("per_symbol_budget must be a tuple")
        seen: set[str] = set()
        for pair in self.per_symbol_budget:
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise PortfolioBacktestError("per_symbol_budget must contain (symbol, Decimal) pairs")
            symbol, budget = pair
            if not isinstance(symbol, str) or not symbol:
                raise PortfolioBacktestError("budget symbol must be a non-empty string")
            if symbol in seen:
                raise PortfolioBacktestError("per_symbol_budget symbols must be unique")
            seen.add(symbol)
            if not isinstance(budget, Decimal) or not budget.is_finite() or budget <= 0:
                raise PortfolioBacktestError("budget must be a positive finite Decimal")

    def budget_for(self, symbol: str) -> Decimal | None:
        for pair in self.per_symbol_budget:
            if pair[0] == symbol:
                return pair[1]
        return None
