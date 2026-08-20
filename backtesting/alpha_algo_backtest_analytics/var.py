"""Historical VaR and CVaR for backtest performance reports (P16).

Value-at-Risk (VaR) and Conditional Value-at-Risk (CVaR / expected
shortfall) are computed by the **historical (non-parametric) order-statistic
method** over a caller-supplied tuple of per-period returns. No distribution
is assumed and no statistical guarantee is implied beyond the chosen model —
these are informational reconstructions of the explicit historical inputs.

Method (fixed and auditable):

- Sort the ``observations`` ascending (most negative first).
- ``k = max(1, floor((1 - confidence) * n))`` is the 1-indexed position of
  the historical quantile; ``var_return`` is the ``k``-th smallest return
  (approximately the ``(1 - confidence)`` quantile).
- ``var_loss = -var_return`` (a non-negative loss magnitude).
- ``cvar_loss = -mean(observations[0:k])`` — the mean of the worst ``k``
  returns (the tail beyond the VaR threshold), a non-negative loss magnitude.

Edge cases: an empty observation set returns ``None``; ``confidence`` must
be an exact ``Decimal`` in the open interval ``(0, 1)``. The metrics are
explicitly **per-period** (no horizon scaling — the caller maps the return
frequency); no annualization is applied.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal, localcontext

from alpha_algo_backtest_analytics.errors import RiskMeasureError

__all__ = [
    "HISTORICAL_VAR_POLICY",
    "DECIMAL_PRECISION",
    "VarCvarMetrics",
    "compute_var_cvar",
]

DECIMAL_PRECISION = 28

HISTORICAL_VAR_POLICY = (
    "Historical (non-parametric) order-statistic VaR/CVaR over per-period "
    "returns. k = max(1, floor((1 - confidence) * n)) selects the quantile "
    "of the ascending-sorted returns; var_loss = -(k-th smallest return); "
    "cvar_loss = -(mean of the worst k returns). Per-period, informational, "
    "no distribution or horizon assumption; empty observations -> None."
)


@dataclass(frozen=True)
class VarCvarMetrics:
    """Historical VaR and CVaR for one return series.

    These are informational reconstructions of the explicit historical
    inputs under the documented method; they imply no statistical guarantee
    and no forward performance.
    """

    confidence: Decimal
    method: str
    observation_count: int
    var_return: Decimal
    var_loss: Decimal
    cvar_loss: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.confidence, Decimal) or not self.confidence.is_finite():
            raise RiskMeasureError("confidence must be a finite Decimal")
        if not (Decimal("0") < self.confidence < Decimal("1")):
            raise RiskMeasureError("confidence must be in the open interval (0, 1)")
        if not isinstance(self.method, str) or not self.method:
            raise RiskMeasureError("method must be a non-empty string")
        if type(self.observation_count) is not int or self.observation_count < 1:
            raise RiskMeasureError("observation_count must be a positive int")
        for name, value in (("var_return", self.var_return), ("var_loss", self.var_loss), ("cvar_loss", self.cvar_loss)):
            if not isinstance(value, Decimal) or not value.is_finite():
                raise RiskMeasureError(f"{name} must be a finite Decimal")
        if self.var_loss < 0:
            raise RiskMeasureError("var_loss must be non-negative")
        if self.cvar_loss < 0:
            raise RiskMeasureError("cvar_loss must be non-negative")
        if self.cvar_loss < self.var_loss:
            raise RiskMeasureError("cvar_loss must be at least var_loss (tail mean cannot beat its own worst point)")


def _validate_returns(returns: tuple[Decimal, ...]) -> None:
    if not isinstance(returns, tuple):
        raise RiskMeasureError("returns must be a tuple of Decimal")
    for value in returns:
        if not isinstance(value, Decimal) or not value.is_finite():
            raise RiskMeasureError("returns must contain only finite Decimals")


def compute_var_cvar(
    returns: tuple[Decimal, ...],
    *,
    confidence: Decimal,
) -> VarCvarMetrics | None:
    """Compute historical VaR and CVaR over per-period returns.

    Returns ``None`` for an empty observation set. Raises
    :class:`RiskMeasureError` for out-of-contract inputs.
    """
    _validate_returns(returns)
    if not isinstance(confidence, Decimal) or not confidence.is_finite():
        raise RiskMeasureError("confidence must be a finite Decimal")
    if not (Decimal("0") < confidence < Decimal("1")):
        raise RiskMeasureError("confidence must be in the open interval (0, 1)")

    n = len(returns)
    if n == 0:
        return None

    with localcontext() as ctx:
        ctx.prec = DECIMAL_PRECISION
        sorted_returns = tuple(sorted(returns))
        # floor semantics: (1-confidence)*n floored, but at least 1
        fraction = (Decimal(1) - confidence) * Decimal(n)
        k = int(fraction.to_integral_value(rounding=ROUND_FLOOR))
        k = max(1, k)
        var_return = sorted_returns[k - 1]
        # Loss magnitudes are clamped at zero: when the quantile/tail return
        # is positive (all gains), the "loss" is zero, never a fabricated
        # negative loss.
        var_loss = -var_return
        if var_loss < 0:
            var_loss = Decimal("0")
        tail = sorted_returns[:k]
        cvar_loss = -(sum(tail, Decimal("0")) / Decimal(len(tail)))
        if cvar_loss < 0:
            cvar_loss = Decimal("0")

    return VarCvarMetrics(
        confidence=confidence,
        method="historical",
        observation_count=n,
        var_return=var_return,
        var_loss=var_loss,
        cvar_loss=cvar_loss,
    )
