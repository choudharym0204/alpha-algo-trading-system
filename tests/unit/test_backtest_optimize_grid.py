from __future__ import annotations

from decimal import Decimal

import pytest

from alpha_algo_backtest_optimize import (
    OptimizationError,
    Parameter,
    ParameterGrid,
    ParameterPoint,
    grid_search,
    select_best,
)


def _objective_that_prefers_sum(point: ParameterPoint) -> Decimal:
    return sum((v for _, v in point.assignments), Decimal("0"))


class TestGridSearch:
    def test_deterministic_lexicographic_order(self) -> None:
        grid = ParameterGrid(
            parameters=(
                Parameter("a", (1, 2)),
                Parameter("b", (10, 20)),
            )
        )
        result = grid_search(grid, _objective_that_prefers_sum)
        # 4 combos: (1,10),(1,20),(2,10),(2,20) in lexicographic order.
        assert len(result.evaluations) == 4
        assert [e.point.assignments for e in result.evaluations] == [
            (("a", 1), ("b", 10)),
            (("a", 1), ("b", 20)),
            (("a", 2), ("b", 10)),
            (("a", 2), ("b", 20)),
        ]
        assert result.best_point.as_dict() == {"a": 2, "b": 20}
        assert result.best_score == Decimal("22")

    def test_tie_breaks_to_first(self) -> None:
        grid = ParameterGrid(parameters=(Parameter("a", (1, 2)),))
        result = grid_search(grid, lambda p: Decimal("5"))
        # Both score 5; first in order (a=1) wins.
        assert result.best_point.as_dict() == {"a": 1}
        assert result.best_score == Decimal("5")

    def test_combination_count(self) -> None:
        grid = ParameterGrid(
            parameters=(Parameter("a", (1, 2, 3)), Parameter("b", ("x", "y")))
        )
        assert grid.combination_count == 6

    def test_empty_values_rejected(self) -> None:
        with pytest.raises(OptimizationError):
            Parameter("a", ())

    def test_duplicate_names_rejected(self) -> None:
        with pytest.raises(OptimizationError):
            ParameterGrid(parameters=(Parameter("a", (1,)), Parameter("a", (2,))))

    def test_empty_grid_rejected(self) -> None:
        with pytest.raises(OptimizationError):
            ParameterGrid(parameters=())

    def test_float_and_int_scores_coerced(self) -> None:
        grid = ParameterGrid(parameters=(Parameter("a", (1, 2)),))
        result = grid_search(grid, lambda p: 0.5)  # float -> Decimal
        assert result.best_score == Decimal("0.5")

    def test_non_numeric_score_rejected(self) -> None:
        grid = ParameterGrid(parameters=(Parameter("a", (1,)),))
        with pytest.raises(OptimizationError):
            grid_search(grid, lambda p: "not-a-number")  # type: ignore[return-value]

    def test_bool_score_rejected(self) -> None:
        grid = ParameterGrid(parameters=(Parameter("a", (1,)),))
        with pytest.raises(OptimizationError):
            grid_search(grid, lambda p: True)  # type: ignore[return-value]

    def test_select_best_empty_rejected(self) -> None:
        with pytest.raises(OptimizationError):
            select_best(())

    def test_repeatable(self) -> None:
        grid = ParameterGrid(parameters=(Parameter("a", (1, 2, 3)), Parameter("b", (5, 7))))
        a = grid_search(grid, _objective_that_prefers_sum)
        b = grid_search(grid, _objective_that_prefers_sum)
        assert a == b


class TestTrainTestSeparation:
    def test_optimize_on_train_evaluate_on_test(self) -> None:
        # Train objective scores higher for small params; test data is separate.
        train_grid = ParameterGrid(parameters=(Parameter("p", (1, 2, 3)),))

        def train_objective(point: ParameterPoint) -> Decimal:
            p = point.as_dict()["p"]
            return Decimal(str(10 - p))  # prefers p=1

        result = grid_search(train_grid, train_objective)
        assert result.best_point.as_dict() == {"p": 1}

        # Out-of-sample: the chosen parameter is evaluated on untouched data.
        test_scores = {1: Decimal("3.0"), 2: Decimal("9.9"), 3: Decimal("1.0")}
        chosen = result.best_point.as_dict()["p"]
        oos_score = test_scores[chosen]
        assert oos_score == Decimal("3.0")
        # The optimizer never saw test_scores (no leakage by construction).
        assert result.best_score == Decimal("9")
