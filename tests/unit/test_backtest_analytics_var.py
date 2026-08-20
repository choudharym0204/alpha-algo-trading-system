from __future__ import annotations

from decimal import Decimal

import pytest

from alpha_algo_backtest_analytics import RiskMeasureError, compute_var_cvar


class TestVarCvar:
    def test_historical_var_is_the_quantile(self) -> None:
        # 100 observations, 95% confidence -> k = floor(0.05 * 100) = 5.
        returns = tuple(sorted(
            Decimal(str(i - 50)) / Decimal("1000") for i in range(100)
        ))
        result = compute_var_cvar(returns, confidence=Decimal("0.95"))
        assert result is not None
        assert result.observation_count == 100
        # The 5th smallest return is the VaR return.
        assert result.var_return == returns[4]
        assert result.var_loss == -returns[4]

    def test_cvar_is_mean_of_worst_tail(self) -> None:
        returns = (Decimal("-0.10"), Decimal("-0.05"), Decimal("0.00"), Decimal("0.01"), Decimal("0.02"))
        # 80% confidence -> k = floor(0.20 * 5) = 1; tail = worst 1 = -0.10.
        result = compute_var_cvar(returns, confidence=Decimal("0.80"))
        assert result is not None
        assert result.var_loss == Decimal("0.10")
        assert result.cvar_loss == Decimal("0.10")

    def test_cvar_at_least_var(self) -> None:
        returns = (Decimal("-0.10"), Decimal("-0.06"), Decimal("-0.02"), Decimal("0.01"), Decimal("0.03"))
        result = compute_var_cvar(returns, confidence=Decimal("0.60"))
        assert result is not None
        # k = floor(0.40*5)=2; var = -0.06; cvar = mean(-0.10, -0.06)=0.08.
        assert result.var_loss == Decimal("0.06")
        assert result.cvar_loss == Decimal("0.08")
        assert result.cvar_loss >= result.var_loss

    def test_empty_returns_none(self) -> None:
        assert compute_var_cvar((), confidence=Decimal("0.95")) is None

    def test_all_gains_zero_loss(self) -> None:
        returns = (Decimal("0.01"), Decimal("0.02"), Decimal("0.03"))
        result = compute_var_cvar(returns, confidence=Decimal("0.95"))
        assert result is not None
        assert result.var_loss == Decimal("0")
        assert result.cvar_loss == Decimal("0")

    def test_confidence_out_of_range_rejected(self) -> None:
        with pytest.raises(RiskMeasureError):
            compute_var_cvar((Decimal("0.01"),), confidence=Decimal("1.0"))
        with pytest.raises(RiskMeasureError):
            compute_var_cvar((Decimal("0.01"),), confidence=Decimal("0"))

    def test_non_finite_return_rejected(self) -> None:
        with pytest.raises(RiskMeasureError):
            compute_var_cvar((Decimal("NaN"),), confidence=Decimal("0.95"))

    def test_deterministic(self) -> None:
        returns = tuple(Decimal(str(i)) / Decimal("100") for i in range(-40, 60))
        a = compute_var_cvar(returns, confidence=Decimal("0.95"))
        b = compute_var_cvar(returns, confidence=Decimal("0.95"))
        assert a == b
