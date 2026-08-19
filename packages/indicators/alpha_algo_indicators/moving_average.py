from __future__ import annotations

from decimal import Decimal
from typing import Iterable


def _to_decimal_series(values: Iterable[Decimal | int | str]) -> list[Decimal]:
    return [value if isinstance(value, Decimal) else Decimal(str(value)) for value in values]


def _validate_period(period: int) -> None:
    if period <= 0:
        raise ValueError("period must be positive")


def simple_moving_average(values: Iterable[Decimal | int | str], *, period: int) -> list[Decimal | None]:
    _validate_period(period)
    series = _to_decimal_series(values)
    results: list[Decimal | None] = []

    for index in range(len(series)):
        if index + 1 < period:
            results.append(None)
            continue
        window = series[index + 1 - period : index + 1]
        results.append(sum(window) / Decimal(period))

    return results


def exponential_moving_average(values: Iterable[Decimal | int | str], *, period: int) -> list[Decimal | None]:
    _validate_period(period)
    series = _to_decimal_series(values)
    results: list[Decimal | None] = []
    multiplier = Decimal(2) / Decimal(period + 1)
    previous: Decimal | None = None

    for index, value in enumerate(series):
        if index + 1 < period:
            results.append(None)
            continue
        if previous is None:
            previous = sum(series[index + 1 - period : index + 1]) / Decimal(period)
        else:
            previous = (value - previous) * multiplier + previous
        results.append(previous)

    return results

