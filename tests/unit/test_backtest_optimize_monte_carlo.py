from __future__ import annotations

from decimal import Decimal

import pytest

from alpha_algo_backtest_optimize import (
    OptimizationError,
    bootstrap_paths,
    bootstrap_summary,
    deterministic_shuffle,
)


class TestMonteCarlo:
    def test_same_seed_identical(self) -> None:
        values = tuple(Decimal(str(i)) for i in range(1, 11))
        a = bootstrap_paths(values, n_paths=50, seed="s1")
        b = bootstrap_paths(values, n_paths=50, seed="s1")
        assert a == b

    def test_different_seed_differentiates(self) -> None:
        values = tuple(Decimal(str(i)) for i in range(1, 11))
        a = bootstrap_paths(values, n_paths=200, seed="s1")
        b = bootstrap_paths(values, n_paths=200, seed="s2")
        assert a != b

    def test_path_count_respected(self) -> None:
        values = (Decimal("1"), Decimal("2"), Decimal("3"))
        paths = bootstrap_paths(values, n_paths=25, seed="s")
        assert len(paths) == 25

    def test_deterministic_ordering(self) -> None:
        values = (Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4"))
        a = bootstrap_paths(values, n_paths=20, seed="ord")
        b = bootstrap_paths(values, n_paths=20, seed="ord")
        assert list(a) == list(b)

    def test_summary_percentiles_ordered(self) -> None:
        values = tuple(Decimal(str(i)) for i in range(1, 21))
        summary = bootstrap_summary(values, n_paths=100, seed="s")
        assert summary.minimum <= summary.p5 <= summary.p50 <= summary.p95 <= summary.maximum
        assert summary.n_paths == 100
        assert summary.seed == "s"

    def test_empty_values_rejected(self) -> None:
        with pytest.raises(OptimizationError):
            bootstrap_paths((), n_paths=5, seed="s")

    def test_empty_seed_rejected(self) -> None:
        with pytest.raises(OptimizationError):
            bootstrap_paths((Decimal("1"),), n_paths=5, seed="")

    def test_nonpositive_paths_rejected(self) -> None:
        with pytest.raises(OptimizationError):
            bootstrap_paths((Decimal("1"),), n_paths=0, seed="s")

    def test_custom_statistic(self) -> None:
        values = (Decimal("1"), Decimal("2"), Decimal("3"))
        paths = bootstrap_paths(values, n_paths=10, seed="s", statistic=lambda xs: max(xs))
        for path in paths:
            assert path <= Decimal("3")

    def test_deterministic_shuffle_is_permutation(self) -> None:
        values = (Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4"), Decimal("5"))
        shuffled = deterministic_shuffle(values, seed="shuf")
        assert sorted(shuffled) == sorted(values)
        assert deterministic_shuffle(values, seed="shuf") == shuffled

    def test_shuffle_different_seed_differs_or_same_length(self) -> None:
        values = tuple(Decimal(str(i)) for i in range(1, 20))
        a = deterministic_shuffle(values, seed="a")
        b = deterministic_shuffle(values, seed="b")
        assert len(a) == len(b) == len(values)
        # Seeds may occasionally produce equal permutations, but for this
        # fixed vector they differ.
        assert a != b
