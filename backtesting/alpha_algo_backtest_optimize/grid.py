"""Deterministic parameter grid search for the backtesting subsystem (P16).

A pure, reproducible grid search over an ordered parameter space. The grid
is evaluated in **deterministic lexicographic order** (``itertools.product``
over ordered value tuples), so process scheduling, hash seeds, and iteration
order can never change the result. Ties are broken in favor of the first
evaluation in that deterministic order.

Train/test separation is a **caller responsibility made explicit by the API**:
the ``objective`` callable receives only whatever data the caller closes over.
To avoid overfitting, the caller must build the objective from training data
only, then evaluate the selected parameters out-of-sample separately — the
optimizer never sees, and never mixes, the two. No parallel execution is used
(sequential only), so there is no scheduling-dependent result aggregation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from itertools import product
from typing import Callable

from alpha_algo_backtest_optimize.errors import OptimizationError

__all__ = [
    "GRID_SEARCH_POLICY",
    "Evaluation",
    "OptimizationResult",
    "Parameter",
    "ParameterGrid",
    "ParameterPoint",
    "evaluate_point",
    "grid_search",
    "select_best",
]

GRID_SEARCH_POLICY = (
    "Deterministic lexicographic grid search (itertools.product over ordered "
    "values). Objective receives one ParameterPoint (training-data closure is "
    "the caller's responsibility). Ties break to the first evaluation in "
    "deterministic order. Sequential only — no parallel scheduling, no shared "
    "mutable state, no random ordering."
)

Score = Decimal | int | float


def _coerce_score(score: Score) -> Decimal:
    if isinstance(score, Decimal):
        if not score.is_finite():
            raise OptimizationError("objective score must be finite")
        return score
    if isinstance(score, bool):
        raise OptimizationError("objective score must be numeric, not bool")
    if isinstance(score, (int, float)):
        value = Decimal(str(score))
        if not value.is_finite():
            raise OptimizationError("objective score must be finite")
        return value
    raise OptimizationError("objective score must be a Decimal, int, or float")


@dataclass(frozen=True)
class Parameter:
    """One search dimension: a name and an ordered, non-empty tuple of values."""

    name: str
    values: tuple

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise OptimizationError("Parameter.name must be a non-empty string")
        if not isinstance(self.values, tuple) or not self.values:
            raise OptimizationError(f"Parameter {self.name!r} values must be a non-empty tuple")


@dataclass(frozen=True)
class ParameterGrid:
    """An ordered collection of search dimensions."""

    parameters: tuple[Parameter, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.parameters, tuple) or not self.parameters:
            raise OptimizationError("ParameterGrid.parameters must be a non-empty tuple of Parameter")
        if not all(isinstance(p, Parameter) for p in self.parameters):
            raise OptimizationError("ParameterGrid.parameters must contain only Parameter")
        names = [p.name for p in self.parameters]
        if len(set(names)) != len(names):
            raise OptimizationError("Parameter names must be unique")

    @property
    def combination_count(self) -> int:
        count = 1
        for parameter in self.parameters:
            count *= len(parameter.values)
        return count


@dataclass(frozen=True)
class ParameterPoint:
    """One concrete parameter assignment, as ordered ``(name, value)`` pairs."""

    assignments: tuple[tuple[str, object], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.assignments, tuple):
            raise OptimizationError("ParameterPoint.assignments must be a tuple")

    def as_dict(self) -> dict[str, object]:
        return dict(self.assignments)


@dataclass(frozen=True)
class Evaluation:
    """One objective evaluation at one parameter point (deterministic order)."""

    point: ParameterPoint
    score: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.point, ParameterPoint):
            raise OptimizationError("Evaluation.point must be a ParameterPoint")
        if not isinstance(self.score, Decimal) or not self.score.is_finite():
            raise OptimizationError("Evaluation.score must be a finite Decimal")


@dataclass(frozen=True)
class OptimizationResult:
    """The complete, ordered result of one grid search."""

    grid: ParameterGrid
    evaluations: tuple[Evaluation, ...]
    best_point: ParameterPoint
    best_score: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.grid, ParameterGrid):
            raise OptimizationError("OptimizationResult.grid must be a ParameterGrid")
        if not isinstance(self.evaluations, tuple) or not self.evaluations:
            raise OptimizationError("OptimizationResult.evaluations must be a non-empty tuple of Evaluation")
        if not all(isinstance(e, Evaluation) for e in self.evaluations):
            raise OptimizationError("OptimizationResult.evaluations must contain only Evaluation")
        if not isinstance(self.best_point, ParameterPoint):
            raise OptimizationError("OptimizationResult.best_point must be a ParameterPoint")
        if not isinstance(self.best_score, Decimal) or not self.best_score.is_finite():
            raise OptimizationError("OptimizationResult.best_score must be a finite Decimal")


def evaluate_point(point: ParameterPoint, objective: Callable[[ParameterPoint], Score]) -> Decimal:
    """Evaluate one point, coercing and validating the returned score."""
    if not isinstance(point, ParameterPoint):
        raise OptimizationError("point must be a ParameterPoint")
    if not callable(objective):
        raise OptimizationError("objective must be callable")
    return _coerce_score(objective(point))


def grid_search(
    grid: ParameterGrid,
    objective: Callable[[ParameterPoint], Score],
) -> OptimizationResult:
    """Evaluate every grid combination in deterministic lexicographic order."""
    if not isinstance(grid, ParameterGrid):
        raise OptimizationError("grid must be a ParameterGrid")
    if not callable(objective):
        raise OptimizationError("objective must be callable")

    names = [p.name for p in grid.parameters]
    value_tuples = [p.values for p in grid.parameters]

    evaluations: list[Evaluation] = []
    for combo in product(*value_tuples):
        point = ParameterPoint(assignments=tuple(zip(names, combo)))
        score = evaluate_point(point, objective)
        evaluations.append(Evaluation(point=point, score=score))

    best = select_best(tuple(evaluations))
    return OptimizationResult(
        grid=grid,
        evaluations=tuple(evaluations),
        best_point=best.point,
        best_score=best.score,
    )


def select_best(
    evaluations: tuple[Evaluation, ...],
) -> Evaluation:
    """Return the highest-scoring evaluation (deterministic tie-break).

    Ties are broken in favor of the first evaluation in the given (already
    deterministic) order — never by dict iteration or hash ordering.
    """
    if not isinstance(evaluations, tuple) or not evaluations:
        raise OptimizationError("evaluations must be a non-empty tuple of Evaluation")
    if not all(isinstance(e, Evaluation) for e in evaluations):
        raise OptimizationError("evaluations must contain only Evaluation")

    best = evaluations[0]
    for evaluation in evaluations[1:]:
        if evaluation.score > best.score:
            best = evaluation
    return best
