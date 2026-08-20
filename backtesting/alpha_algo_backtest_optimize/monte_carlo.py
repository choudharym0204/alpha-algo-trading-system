"""Reproducible Monte Carlo simulation for the backtesting subsystem (P16).

Monte Carlo is implemented **only in a reproducible form**: every resample
uses a deterministic PRNG derived from an explicit seed (SHA-256 of
``"seed:counter"`` — no ``random`` module, no global random state, no wall
clock). For a fixed ``(values, seed, n_paths, statistic)`` the output is
bit-identical across runs, machines, and Python hash seeds.

Two primitives are provided:

- :func:`deterministic_shuffle` — a seeded Fisher-Yates shuffle (for
  trade-order reshuffling).
- :func:`bootstrap_paths` / :func:`bootstrap_summary` — seeded bootstrap
  resampling (with replacement) of a value sequence, yielding a deterministic
  summary (mean, min, max, and p5/p50/p95 percentiles).

The bootstrap is over a sequence of **per-period returns or per-trade P&L**.
The caller supplies the statistic (default: sum). For returns the caller
should compound (e.g. ``lambda xs: prod(1 + x for x in xs) - 1``); the
package does not assume a compounding convention.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import Callable

from alpha_algo_backtest_optimize.errors import OptimizationError

__all__ = [
    "MONTE_CARLO_POLICY",
    "DECIMAL_PRECISION",
    "MonteCarloSummary",
    "bootstrap_paths",
    "bootstrap_summary",
    "deterministic_shuffle",
]

DECIMAL_PRECISION = 28

MONTE_CARLO_POLICY = (
    "Reproducible Monte Carlo via a deterministic SHA-256-derived PRNG keyed "
    "on 'seed:counter' (no random module, no global state, no wall clock). "
    "Fixed (values, seed, n_paths, statistic) -> identical output. Bootstrap "
    "resamples with replacement; summary reports mean/min/max and p5/p50/p95 "
    "percentiles in deterministic order."
)


def _rand_index(seed: str, counter: int, bound: int) -> int:
    """Deterministic integer in ``[0, bound)`` derived from ``seed:counter``."""
    digest = hashlib.sha256(f"{seed}:{counter}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:8], "big")
    return value % bound


def _validate_values(values: tuple[Decimal, ...]) -> None:
    if not isinstance(values, tuple) or not values:
        raise OptimizationError("values must be a non-empty tuple of Decimal")
    for value in values:
        if not isinstance(value, Decimal) or not value.is_finite():
            raise OptimizationError("values must contain only finite Decimals")


def _validate_seed(seed: str) -> None:
    if not isinstance(seed, str) or not seed:
        raise OptimizationError("seed must be a non-empty string")


def deterministic_shuffle(values: tuple[Decimal, ...], *, seed: str) -> tuple[Decimal, ...]:
    """Return a seeded Fisher-Yates shuffle of ``values`` (deterministic)."""
    _validate_values(values)
    _validate_seed(seed)

    items = list(values)
    n = len(items)
    for i in range(n - 1, 0, -1):
        j = _rand_index(seed, i, i + 1)
        items[i], items[j] = items[j], items[i]
    return tuple(items)


def bootstrap_paths(
    values: tuple[Decimal, ...],
    *,
    n_paths: int,
    seed: str,
    statistic: Callable[[tuple[Decimal, ...]], Decimal] | None = None,
) -> tuple[Decimal, ...]:
    """Return ``n_paths`` bootstrap statistics in deterministic path order.

    Each path resamples ``len(values)`` values with replacement and applies
    ``statistic`` (default: sum). Path order is ``path = 0, 1, ..., n_paths-1``
    and each draw uses a per-``(path, draw)`` counter, so the result is
    reproducible and its ordering is independent of process scheduling.
    """
    _validate_values(values)
    _validate_seed(seed)
    if type(n_paths) is not int or n_paths < 1:
        raise OptimizationError("n_paths must be a positive int")
    if statistic is not None and not callable(statistic):
        raise OptimizationError("statistic must be callable or None")

    fn = statistic if statistic is not None else (lambda xs: sum(xs, Decimal("0")))
    n = len(values)
    results: list[Decimal] = []
    with localcontext() as ctx:
        ctx.prec = DECIMAL_PRECISION
        for path in range(n_paths):
            sample = tuple(values[_rand_index(seed, path * n + draw, n)] for draw in range(n))
            result = fn(sample)
            if not isinstance(result, Decimal) or not result.is_finite():
                raise OptimizationError("statistic must return a finite Decimal")
            results.append(result)
    return tuple(results)


def _percentile(sorted_values: tuple[Decimal, ...], quantile: Decimal) -> Decimal:
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    position = (quantile * Decimal(n - 1)).to_integral_value()
    return sorted_values[int(position)]


@dataclass(frozen=True)
class MonteCarloSummary:
    """Deterministic summary of a seeded bootstrap simulation.

    A Monte Carlo summary is a hypothetical reconstruction of the explicit
    inputs under a documented resampling model; it implies no statistical
    guarantee and no forward performance.
    """

    seed: str
    n_paths: int
    statistic_name: str
    mean: Decimal
    minimum: Decimal
    maximum: Decimal
    p5: Decimal
    p50: Decimal
    p95: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.seed, str) or not self.seed:
            raise OptimizationError("seed must be a non-empty string")
        if type(self.n_paths) is not int or self.n_paths < 1:
            raise OptimizationError("n_paths must be a positive int")
        if not isinstance(self.statistic_name, str) or not self.statistic_name:
            raise OptimizationError("statistic_name must be a non-empty string")
        for name, value in (
            ("mean", self.mean),
            ("minimum", self.minimum),
            ("maximum", self.maximum),
            ("p5", self.p5),
            ("p50", self.p50),
            ("p95", self.p95),
        ):
            if not isinstance(value, Decimal) or not value.is_finite():
                raise OptimizationError(f"{name} must be a finite Decimal")


def bootstrap_summary(
    values: tuple[Decimal, ...],
    *,
    n_paths: int,
    seed: str,
    statistic: Callable[[tuple[Decimal, ...]], Decimal] | None = None,
    statistic_name: str = "sum",
) -> MonteCarloSummary:
    """Run a seeded bootstrap and summarize its deterministic distribution."""
    _validate_seed(seed)
    if not isinstance(statistic_name, str) or not statistic_name:
        raise OptimizationError("statistic_name must be a non-empty string")

    paths = bootstrap_paths(values, n_paths=n_paths, seed=seed, statistic=statistic)
    sorted_paths = tuple(sorted(paths))
    count = Decimal(len(sorted_paths))

    with localcontext() as ctx:
        ctx.prec = DECIMAL_PRECISION
        mean = sum(paths, Decimal("0")) / count
        minimum = sorted_paths[0]
        maximum = sorted_paths[-1]
        p5 = _percentile(sorted_paths, Decimal("0.05"))
        p50 = _percentile(sorted_paths, Decimal("0.50"))
        p95 = _percentile(sorted_paths, Decimal("0.95"))

    return MonteCarloSummary(
        seed=seed,
        n_paths=n_paths,
        statistic_name=statistic_name,
        mean=mean,
        minimum=minimum,
        maximum=maximum,
        p5=p5,
        p50=p50,
        p95=p95,
    )
