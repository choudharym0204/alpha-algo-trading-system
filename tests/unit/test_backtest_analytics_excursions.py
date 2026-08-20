from __future__ import annotations

from decimal import Decimal

import pytest

from alpha_algo_backtest_analytics import (
    ExcursionError,
    ExcursionPoint,
    ExcursionSide,
    compute_excursions,
)
from tests.unit.backtest_p16_test_support import utc


class TestExcursions:
    def test_long_mfe_mae_from_path(self) -> None:
        path = (
            ExcursionPoint(timestamp=utc(2026, 1, 1, 9, 1), high=Decimal("105"), low=Decimal("98")),
            ExcursionPoint(timestamp=utc(2026, 1, 1, 9, 2), high=Decimal("108"), low=Decimal("95")),
        )
        result = compute_excursions(
            side=ExcursionSide.LONG,
            entry_timestamp=utc(2026, 1, 1, 9, 0),
            exit_timestamp=utc(2026, 1, 1, 9, 3),
            entry_price=Decimal("100"),
            exit_price=Decimal("102"),
            path=path,
        )
        # max high = 108, min low = 95 -> mfe = 8, mae = -5.
        assert result.mfe == Decimal("8")
        assert result.mae == Decimal("-5")

    def test_no_path_uses_exit_only(self) -> None:
        result = compute_excursions(
            side=ExcursionSide.LONG,
            entry_timestamp=utc(2026, 1, 1, 9, 0),
            exit_timestamp=utc(2026, 1, 1, 9, 3),
            entry_price=Decimal("100"),
            exit_price=Decimal("102"),
            path=(),
        )
        assert result.mfe == Decimal("2")
        assert result.mae == Decimal("0")

    def test_short_semantics_mirror(self) -> None:
        path = (
            ExcursionPoint(timestamp=utc(2026, 1, 1, 9, 1), high=Decimal("103"), low=Decimal("90")),
        )
        result = compute_excursions(
            side=ExcursionSide.SHORT,
            entry_timestamp=utc(2026, 1, 1, 9, 0),
            exit_timestamp=utc(2026, 1, 1, 9, 3),
            entry_price=Decimal("100"),
            exit_price=Decimal("96"),
            path=path,
        )
        # favorable = entry - min(90) = 10; adverse = entry - max(103) = -3.
        assert result.mfe == Decimal("10")
        assert result.mae == Decimal("-3")

    def test_records_before_entry_are_ignored(self) -> None:
        path = (
            ExcursionPoint(timestamp=utc(2026, 1, 1, 8, 59), high=Decimal("200"), low=Decimal("1")),
        )
        result = compute_excursions(
            side=ExcursionSide.LONG,
            entry_timestamp=utc(2026, 1, 1, 9, 0),
            exit_timestamp=utc(2026, 1, 1, 9, 3),
            entry_price=Decimal("100"),
            exit_price=Decimal("102"),
            path=path,
        )
        assert result.mfe == Decimal("2")
        assert result.mae == Decimal("0")

    def test_records_after_exit_are_ignored(self) -> None:
        path = (
            ExcursionPoint(timestamp=utc(2026, 1, 1, 9, 5), high=Decimal("500"), low=Decimal("1")),
        )
        result = compute_excursions(
            side=ExcursionSide.LONG,
            entry_timestamp=utc(2026, 1, 1, 9, 0),
            exit_timestamp=utc(2026, 1, 1, 9, 3),
            entry_price=Decimal("100"),
            exit_price=Decimal("102"),
            path=path,
        )
        assert result.mfe == Decimal("2")
        assert result.mae == Decimal("0")

    def test_mfe_nonnegative_mae_nonpositive_always(self) -> None:
        result = compute_excursions(
            side=ExcursionSide.LONG,
            entry_timestamp=utc(2026, 1, 1, 9, 0),
            exit_timestamp=utc(2026, 1, 1, 9, 3),
            entry_price=Decimal("100"),
            exit_price=Decimal("90"),
            path=(),
        )
        assert result.mfe >= 0
        assert result.mae <= 0

    def test_entry_after_exit_rejected(self) -> None:
        with pytest.raises(ExcursionError):
            compute_excursions(
                side=ExcursionSide.LONG,
                entry_timestamp=utc(2026, 1, 1, 9, 3),
                exit_timestamp=utc(2026, 1, 1, 9, 0),
                entry_price=Decimal("100"),
                exit_price=Decimal("102"),
                path=(),
            )

    def test_nonpositive_price_rejected(self) -> None:
        with pytest.raises(ExcursionError):
            compute_excursions(
                side=ExcursionSide.LONG,
                entry_timestamp=utc(2026, 1, 1, 9, 0),
                exit_timestamp=utc(2026, 1, 1, 9, 3),
                entry_price=Decimal("0"),
                exit_price=Decimal("102"),
                path=(),
            )

    def test_deterministic(self) -> None:
        path = (ExcursionPoint(timestamp=utc(2026, 1, 1, 9, 1), high=Decimal("105"), low=Decimal("98")),)
        kwargs = dict(
            side=ExcursionSide.LONG,
            entry_timestamp=utc(2026, 1, 1, 9, 0),
            exit_timestamp=utc(2026, 1, 1, 9, 3),
            entry_price=Decimal("100"),
            exit_price=Decimal("102"),
            path=path,
        )
        assert compute_excursions(**kwargs) == compute_excursions(**kwargs)
