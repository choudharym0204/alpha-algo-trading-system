from __future__ import annotations

from decimal import Decimal

import pytest

from alpha_algo_backtest_analytics import RiskMeasureError, compute_alpha_beta


class TestAlphaBeta:
    def test_beta_one_when_identical(self) -> None:
        series = (Decimal("0.01"), Decimal("0.02"), Decimal("-0.01"), Decimal("0.03"))
        result = compute_alpha_beta(
            series, series,
            risk_free_rate_per_period=Decimal("0"),
            benchmark_identity="bench",
            frequency="daily",
        )
        assert result.beta == Decimal("1")
        assert result.alpha == Decimal("0")

    def test_beta_scales(self) -> None:
        benchmark = (Decimal("0.01"), Decimal("-0.01"), Decimal("0.02"), Decimal("0.00"))
        portfolio = tuple(Decimal(2) * r for r in benchmark)
        result = compute_alpha_beta(
            portfolio, benchmark,
            risk_free_rate_per_period=Decimal("0"),
            benchmark_identity="bench",
            frequency="daily",
        )
        assert result.beta == Decimal("2")

    def test_alpha_captures_excess_over_rf(self) -> None:
        benchmark = (Decimal("0.01"), Decimal("0.02"), Decimal("0.01"))
        portfolio = (Decimal("0.03"), Decimal("0.04"), Decimal("0.03"))
        result = compute_alpha_beta(
            portfolio, benchmark,
            risk_free_rate_per_period=Decimal("0"),
            benchmark_identity="bench",
            frequency="daily",
        )
        # beta = 1 (perfectly correlated), alpha = mean_p - mean_b = 0.02.
        assert result.beta == Decimal("1")
        assert result.alpha == Decimal("0.02")

    def test_flat_benchmark_is_undefined(self) -> None:
        benchmark = (Decimal("0.01"), Decimal("0.01"), Decimal("0.01"))
        portfolio = (Decimal("0.01"), Decimal("0.02"), Decimal("-0.01"))
        result = compute_alpha_beta(
            portfolio, benchmark,
            risk_free_rate_per_period=Decimal("0"),
            benchmark_identity="bench",
            frequency="daily",
        )
        assert result.beta is None
        assert result.alpha is None

    def test_insufficient_observations_undefined(self) -> None:
        result = compute_alpha_beta(
            (Decimal("0.01"),), (Decimal("0.01"),),
            risk_free_rate_per_period=Decimal("0"),
            benchmark_identity="bench",
            frequency="daily",
        )
        assert result.beta is None
        assert result.alpha is None

    def test_misaligned_lengths_rejected(self) -> None:
        with pytest.raises(RiskMeasureError):
            compute_alpha_beta(
                (Decimal("0.01"), Decimal("0.02")), (Decimal("0.01"),),
                risk_free_rate_per_period=Decimal("0"),
                benchmark_identity="bench",
                frequency="daily",
            )

    def test_missing_identity_rejected(self) -> None:
        with pytest.raises(RiskMeasureError):
            compute_alpha_beta(
                (Decimal("0.01"), Decimal("0.02")), (Decimal("0.01"), Decimal("0.02")),
                risk_free_rate_per_period=Decimal("0"),
                benchmark_identity="",
                frequency="daily",
            )

    def test_negative_rf_rejected(self) -> None:
        with pytest.raises(RiskMeasureError):
            compute_alpha_beta(
                (Decimal("0.01"), Decimal("0.02")), (Decimal("0.01"), Decimal("0.02")),
                risk_free_rate_per_period=Decimal("-0.01"),
                benchmark_identity="bench",
                frequency="daily",
            )

    def test_deterministic(self) -> None:
        b = (Decimal("0.01"), Decimal("-0.01"), Decimal("0.02"), Decimal("0.00"), Decimal("0.015"))
        p = (Decimal("0.015"), Decimal("-0.005"), Decimal("0.03"), Decimal("0.002"), Decimal("0.02"))
        kwargs = dict(risk_free_rate_per_period=Decimal("0"), benchmark_identity="bench", frequency="daily")
        assert compute_alpha_beta(p, b, **kwargs) == compute_alpha_beta(p, b, **kwargs)
