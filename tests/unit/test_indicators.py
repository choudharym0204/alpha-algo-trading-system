from __future__ import annotations

from decimal import Decimal

import pytest

from alpha_algo_indicators import exponential_moving_average, simple_moving_average


def test_simple_moving_average_is_deterministic() -> None:
    values = [Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4")]

    result = simple_moving_average(values, period=3)

    assert result == [None, None, Decimal("2"), Decimal("3")]


def test_exponential_moving_average_is_deterministic() -> None:
    values = [Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4")]

    result = exponential_moving_average(values, period=3)

    assert result == [None, None, Decimal("2"), Decimal("3.0")]


def test_moving_average_rejects_invalid_period() -> None:
    with pytest.raises(ValueError, match="period must be positive"):
        simple_moving_average([Decimal("1")], period=0)

    with pytest.raises(ValueError, match="period must be positive"):
        exponential_moving_average([Decimal("1")], period=-1)


def test_moving_average_does_not_mutate_input() -> None:
    values = [Decimal("1"), Decimal("2"), Decimal("3")]

    simple_moving_average(values, period=2)
    exponential_moving_average(values, period=2)

    assert values == [Decimal("1"), Decimal("2"), Decimal("3")]

