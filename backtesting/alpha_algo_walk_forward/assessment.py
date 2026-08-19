"""Overfitting assessment for the walk-forward testing harness (P7-003).

``assess_overfitting`` emits fixed-threshold, informational flags over the
aggregate and the periods. No auto-reject: nothing raises, blocks, or
filters based on flags, and this package has no execution or LIVE surface.
All thresholds are fixed named constants - changing any is a contract
change, not a runtime knob. Degenerate inputs (zero OOS trades, fewer than
3 periods) cap ``overfitting_risk`` at LOW with explicit reasons and never
crash; flags are always computed and reported so the cap can never be
mistaken for "flags cleared".
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from enum import StrEnum
from typing import Mapping

from alpha_algo_backtest_engine import DECIMAL_PRECISION

from alpha_algo_walk_forward.aggregate import WalkForwardAggregate
from alpha_algo_walk_forward.errors import WalkForwardError
from alpha_algo_walk_forward.results import WindowBacktestResult

__all__ = [
    "DEGRADATION_THRESHOLD",
    "DEPENDENCY_CV_THRESHOLD",
    "LOW_TRADE_COUNT_THRESHOLD",
    "MAX_RETURN_SANITY_BOUND",
    "MIN_PERIODS_FOR_ASSESSMENT",
    "OVERFITTING_FLAG_NAMES",
    "OVERFITTING_FLAG_POLICY",
    "OverfittingAssessment",
    "OverfittingFlag",
    "OverfittingRisk",
    "assess_overfitting",
]

OVERFITTING_FLAG_POLICY = (
    "Fixed-threshold, informational flags over the aggregate and the periods. No "
    "auto-reject: nothing raises, blocks, or filters based on flags; LIVE is already "
    "disabled and this package has no execution surface. All thresholds are fixed "
    "named constants - changing any is a contract change. Degenerate inputs (zero "
    "OOS trades, fewer than 3 periods) cap overfitting_risk at LOW with explicit "
    "reasons and never crash; flags are always computed and reported."
)

DEGRADATION_THRESHOLD = Decimal("0.5")
LOW_TRADE_COUNT_THRESHOLD = 30
MAX_RETURN_SANITY_BOUND = Decimal("100")
DEPENDENCY_CV_THRESHOLD = Decimal("1.0")
MIN_PERIODS_FOR_ASSESSMENT = 3

OVERFITTING_FLAG_NAMES: tuple[str, ...] = (
    "degradation_total_return",
    "degradation_win_rate",
    "degradation_profit_factor",
    "degradation_max_drawdown",
    "degradation_sharpe_ratio",
    "low_oos_trade_count",
    "unrealistic_oos_return",
    "high_period_dependency",
)

class OverfittingRisk(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


_FLAG_SEVERITIES: Mapping[str, OverfittingRisk] = {
    "degradation_total_return": OverfittingRisk.HIGH,
    "degradation_win_rate": OverfittingRisk.HIGH,
    "degradation_profit_factor": OverfittingRisk.HIGH,
    "degradation_max_drawdown": OverfittingRisk.HIGH,
    "degradation_sharpe_ratio": OverfittingRisk.HIGH,
    "low_oos_trade_count": OverfittingRisk.MEDIUM,
    "unrealistic_oos_return": OverfittingRisk.HIGH,
    "high_period_dependency": OverfittingRisk.MEDIUM,
}

# StrEnum members compare as strings ("HIGH" < "MEDIUM" alphabetically), so
# max() over members is wrong; rank explicitly instead.
_SEVERITY_RANK: Mapping[OverfittingRisk, int] = {
    OverfittingRisk.LOW: 0,
    OverfittingRisk.MEDIUM: 1,
    OverfittingRisk.HIGH: 2,
}

_FLAG_DESCRIPTIONS: Mapping[str, str] = {
    "degradation_total_return": "OOS total_return degradation exceeds the fixed threshold",
    "degradation_win_rate": "OOS win_rate degradation exceeds the fixed threshold",
    "degradation_profit_factor": "OOS profit_factor degradation exceeds the fixed threshold",
    "degradation_max_drawdown": "OOS max_drawdown degradation exceeds the fixed threshold",
    "degradation_sharpe_ratio": "OOS sharpe_ratio degradation exceeds the fixed threshold",
    "low_oos_trade_count": "Mean OOS trade count is below the fixed minimum",
    "unrealistic_oos_return": "A single OOS window return exceeds the fixed sanity bound",
    "high_period_dependency": "OOS total_return coefficient of variation exceeds the fixed threshold",
}


@dataclass(frozen=True)
class OverfittingFlag:
    """One informational flag. ``detail`` carries measured values when triggered."""

    name: str
    description: str
    triggered: bool
    severity: OverfittingRisk
    detail: str | None

    def __post_init__(self) -> None:
        if self.name not in OVERFITTING_FLAG_NAMES:
            raise WalkForwardError(f"flag name {self.name!r} is not a member of OVERFITTING_FLAG_NAMES")
        if not isinstance(self.description, str) or not self.description.strip():
            raise WalkForwardError("description must be a non-empty string")
        if type(self.triggered) is not bool:
            raise WalkForwardError("triggered must be a bool")
        if not isinstance(self.severity, OverfittingRisk):
            raise WalkForwardError("severity must be an OverfittingRisk member")
        if self.detail is not None and not isinstance(self.detail, str):
            raise WalkForwardError("detail must be None or a string")


@dataclass(frozen=True)
class OverfittingAssessment:
    """The complete, immutable overfitting assessment.

    ``flags`` always contains every flag in ``OVERFITTING_FLAG_NAMES``
    order (triggered or not); ``reasons`` is always non-empty and
    deterministic.
    """

    overfitting_risk: OverfittingRisk
    flags: tuple[OverfittingFlag, ...]
    reasons: tuple[str, ...]
    period_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.overfitting_risk, OverfittingRisk):
            raise WalkForwardError("overfitting_risk must be an OverfittingRisk member")
        if not isinstance(self.flags, tuple) or len(self.flags) != len(OVERFITTING_FLAG_NAMES):
            raise WalkForwardError("flags must contain exactly one OverfittingFlag per OVERFITTING_FLAG_NAMES")
        for flag, expected in zip(self.flags, OVERFITTING_FLAG_NAMES):
            if not isinstance(flag, OverfittingFlag):
                raise WalkForwardError("flags entries must be OverfittingFlag")
            if flag.name != expected:
                raise WalkForwardError(f"flags must be in OVERFITTING_FLAG_NAMES order; expected {expected!r}, got {flag.name!r}")
        if not isinstance(self.reasons, tuple) or not self.reasons:
            raise WalkForwardError("reasons must be a non-empty tuple of strings")
        if not all(isinstance(reason, str) and reason.strip() for reason in self.reasons):
            raise WalkForwardError("reasons entries must be non-empty strings")
        if type(self.period_count) is not int or self.period_count < 0:
            raise WalkForwardError("period_count must be a non-negative int")


def _flag(name: str, triggered: bool, detail: str | None) -> OverfittingFlag:
    return OverfittingFlag(
        name=name,
        description=_FLAG_DESCRIPTIONS[name],
        triggered=triggered,
        severity=_FLAG_SEVERITIES[name],
        detail=detail,
    )


def assess_overfitting(
    *,
    periods: tuple[WindowBacktestResult, ...],
    aggregate: WalkForwardAggregate,
) -> OverfittingAssessment:
    """Assess overfitting risk (pure, deterministic, never crashes).

    Flags are computed for every metric and every threshold; the composite
    ``overfitting_risk`` follows the fixed decision table: zero OOS trades
    or fewer than ``MIN_PERIODS_FOR_ASSESSMENT`` periods cap the risk at
    LOW with explicit reasons; otherwise the risk is the highest severity
    among triggered flags (LOW when none trigger). Flags always auto-reject
    nothing.
    """
    if not isinstance(periods, tuple) or not periods:
        raise WalkForwardError("periods must be a non-empty tuple of WindowBacktestResult")
    if not all(isinstance(period, WindowBacktestResult) for period in periods):
        raise WalkForwardError("periods must contain only WindowBacktestResult")
    if not isinstance(aggregate, WalkForwardAggregate):
        raise WalkForwardError("aggregate must be a WalkForwardAggregate")
    if aggregate.period_count != len(periods):
        raise WalkForwardError("aggregate.period_count must equal len(periods)")

    by_metric = {aggregate_entry.metric: aggregate_entry for aggregate_entry in aggregate.metrics}
    period_count = len(periods)

    # Degradation flags (one per scale-free metric).
    flags: list[OverfittingFlag] = []
    for metric in (
        "total_return",
        "win_rate",
        "profit_factor",
        "max_drawdown",
        "sharpe_ratio",
    ):
        entry = by_metric[metric]
        degradation = entry.degradation
        triggered = degradation is not None and degradation > DEGRADATION_THRESHOLD
        detail = None
        if triggered:
            detail = (
                f"degradation={degradation} (> {DEGRADATION_THRESHOLD}); "
                f"IS mean={entry.is_stats.mean}; OOS mean={entry.oos_stats.mean}"
            )
        flags.append(_flag(f"degradation_{metric}", triggered, detail))

    # Low OOS trade count (cross-window mean).
    trade_entry = by_metric["trade_count"]
    mean_oos_trades = trade_entry.oos_stats.mean
    low_trades = mean_oos_trades is not None and mean_oos_trades < Decimal(LOW_TRADE_COUNT_THRESHOLD)
    flags.append(
        _flag(
            "low_oos_trade_count",
            low_trades,
            f"mean OOS trades={mean_oos_trades} (< {LOW_TRADE_COUNT_THRESHOLD})" if low_trades else None,
        )
    )

    # Unrealistic single-window OOS return.
    max_oos_return = max(period.oos_metrics.total_return for period in periods)
    unrealistic = max_oos_return > MAX_RETURN_SANITY_BOUND
    flags.append(
        _flag(
            "unrealistic_oos_return",
            unrealistic,
            f"max OOS window return={max_oos_return} (> {MAX_RETURN_SANITY_BOUND})" if unrealistic else None,
        )
    )

    # OOS total_return coefficient of variation (assessable only with >= 2
    # contributing windows and a positive mean).
    total_return_entry = by_metric["total_return"]
    oos_stdev = total_return_entry.oos_stats.stdev
    oos_mean = total_return_entry.oos_stats.mean
    cv: Decimal | None = None
    if oos_stdev is not None and oos_mean is not None and oos_mean > 0:
        with localcontext() as ctx:
            ctx.prec = DECIMAL_PRECISION
            cv = oos_stdev / oos_mean
    dependency = cv is not None and cv > DEPENDENCY_CV_THRESHOLD
    flags.append(
        _flag(
            "high_period_dependency",
            dependency,
            f"OOS total_return CV={cv} (> {DEPENDENCY_CV_THRESHOLD}); stdev={oos_stdev}; mean={oos_mean}"
            if dependency
            else None,
        )
    )

    triggered_flags = [flag for flag in flags if flag.triggered]

    # Decision table (fixed order).
    reasons: list[str] = []
    degenerate = False
    if mean_oos_trades is not None and mean_oos_trades == 0:
        overfitting_risk = OverfittingRisk.LOW
        reasons.append("zero OOS trades; nothing assessable")
        degenerate = True
    elif period_count < MIN_PERIODS_FOR_ASSESSMENT:
        overfitting_risk = OverfittingRisk.LOW
        reasons.append(f"fewer than {MIN_PERIODS_FOR_ASSESSMENT} periods; cross-window statistics are degenerate")
        degenerate = True
    elif triggered_flags:
        highest = max(triggered_flags, key=lambda flag: _SEVERITY_RANK[flag.severity])
        overfitting_risk = highest.severity
    else:
        overfitting_risk = OverfittingRisk.LOW

    for metric in (
        "total_return",
        "win_rate",
        "profit_factor",
        "max_drawdown",
        "sharpe_ratio",
    ):
        if by_metric[metric].degradation is None:
            reasons.append(f"degradation not assessable for {metric}: IS mean is zero or undefined")

    for flag in triggered_flags:
        reasons.append(flag.detail if flag.detail is not None else flag.description)

    if not triggered_flags and not degenerate:
        reasons.append("no overfitting flags triggered")

    return OverfittingAssessment(
        overfitting_risk=overfitting_risk,
        flags=tuple(flags),
        reasons=tuple(reasons),
        period_count=period_count,
    )
