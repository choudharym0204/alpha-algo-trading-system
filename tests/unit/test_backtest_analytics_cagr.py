from __future__ import annotations

from decimal import Decimal

import pytest

from alpha_algo_backtest_analytics import AnnualizationError, compute_cagr


class TestCagr:
    def test_one_year_flat_ten_percent(self) -> None:
        # 100 -> 110 over 1 year (12 monthly periods, 12 ppy) => 10% CAGR.
        result = compute_cagr(
            beginning_value=Decimal("100"),
            ending_value=Decimal("110"),
            periods=12,
            periods_per_year=12,
        )
        assert result.cagr == Decimal("0.10")
        assert result.total_return == Decimal("0.10")

    def test_partial_year_compounds_to_full_year_rate(self) -> None:
        # 100 -> 110 over 6 months (6 periods, 12 ppy) => (1.10)^2 - 1 = 0.21.
        result = compute_cagr(
            beginning_value=Decimal("100"),
            ending_value=Decimal("110"),
            periods=6,
            periods_per_year=12,
        )
        assert result.cagr == Decimal("0.21")

    def test_multi_year(self) -> None:
        # 100 -> 121 over 2 years (24 monthly, 12 ppy) => (1.21)^(1/2)-1 = 0.10.
        result = compute_cagr(
            beginning_value=Decimal("100"),
            ending_value=Decimal("121"),
            periods=24,
            periods_per_year=12,
        )
        assert result.cagr == Decimal("0.10")

    def test_flat_return_is_zero(self) -> None:
        result = compute_cagr(
            beginning_value=Decimal("100"),
            ending_value=Decimal("100"),
            periods=12,
            periods_per_year=12,
        )
        assert result.cagr == Decimal("0")

    def test_loss_is_negative(self) -> None:
        result = compute_cagr(
            beginning_value=Decimal("100"),
            ending_value=Decimal("90"),
            periods=12,
            periods_per_year=12,
        )
        assert result.cagr == Decimal("-0.10")

    def test_insufficient_duration_returns_none(self) -> None:
        result = compute_cagr(
            beginning_value=Decimal("100"),
            ending_value=Decimal("110"),
            periods=0,
            periods_per_year=12,
        )
        assert result.cagr is None

    def test_zero_capital_is_rejected(self) -> None:
        with pytest.raises(AnnualizationError):
            compute_cagr(
                beginning_value=Decimal("0"),
                ending_value=Decimal("110"),
                periods=12,
                periods_per_year=12,
            )

    def test_negative_capital_is_rejected(self) -> None:
        with pytest.raises(AnnualizationError):
            compute_cagr(
                beginning_value=Decimal("100"),
                ending_value=Decimal("-10"),
                periods=12,
                periods_per_year=12,
            )

    def test_invalid_periods_per_year_rejected(self) -> None:
        with pytest.raises(AnnualizationError):
            compute_cagr(
                beginning_value=Decimal("100"),
                ending_value=Decimal("110"),
                periods=12,
                periods_per_year=0,
            )

    def test_deterministic(self) -> None:
        kwargs = dict(
            beginning_value=Decimal("100"),
            ending_value=Decimal("117.53"),
            periods=37,
            periods_per_year=252,
        )
        assert compute_cagr(**kwargs) == compute_cagr(**kwargs)
