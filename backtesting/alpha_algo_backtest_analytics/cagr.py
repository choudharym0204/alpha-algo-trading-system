"""CAGR (compound annual growth rate) for backtest performance reports (P16).

CAGR is the geometric annualized return that, when compounded over the
observed period, reproduces the observed total return. It is a pure,
deterministic function of a beginning value, an ending value, a count of
elapsed periods, and an explicit periods-per-year annualization basis.

Design rules:

- Exact ``Decimal`` under a fixed ``localcontext`` (28 digits). ``Decimal``
  supports fractional powers only via the natural log/exp route
  (``Decimal.ln`` / ``Decimal.exp``, available on Python 3.11+), so CAGR is
  computed as ``exp(ln(ratio) * (pp_y / periods)) - 1`` — never via ``float``
  or ``math``.
- Non-positive beginning/ending capital is a hard error: a negative capital
  makes a growth rate undefined, and returning a fabricated number would be
  worse than failing loudly.
- Insufficient duration (``periods <= 0``) returns ``None`` (undefined, not
  zero): a CAGR over an empty span is not defined.
- ``periods_per_year`` is an explicit caller-supplied basis (e.g. 252 for
  daily bars, 12 for monthly, 4 for quarterly). The analytics package has no
  calendar model, so the caller decides the annualization convention — the
  engine never assumes one.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext

from alpha_algo_backtest_analytics.errors import AnnualizationError

__all__ = ["CAGR_POLICY", "CagrResult", "DECIMAL_PRECISION", "compute_cagr"]

DECIMAL_PRECISION = 28

CAGR_POLICY = (
    "CAGR = (ending/beginning) ** (periods_per_year/periods) - 1, computed "
    "exactly as exp(ln(ending/beginning) * periods_per_year / periods) - 1 "
    "under Decimal precision 28. periods is the count of elapsed return "
    "periods; periods_per_year is an explicit caller-supplied annualization "
    "basis (the package has no calendar model). Undefined when periods <= 0 "
    "(returns None); non-positive beginning/ending capital raises "
    "AnnualizationError (a growth rate is genuinely undefined there)."
)


@dataclass(frozen=True)
class CagrResult:
    """The compound annual growth rate for one return series.

    A CAGR is a hypothetical reconstruction of the explicit historical
    inputs under the documented annualization basis; it is not evidence of
    profitability and implies no forward performance.
    """

    beginning_value: Decimal
    ending_value: Decimal
    total_return: Decimal
    periods: int
    periods_per_year: int
    cagr: Decimal | None

    def __post_init__(self) -> None:
        for name, value in (("beginning_value", self.beginning_value), ("ending_value", self.ending_value)):
            if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
                raise AnnualizationError(f"{name} must be a positive finite Decimal")
        if not isinstance(self.total_return, Decimal) or not self.total_return.is_finite():
            raise AnnualizationError("total_return must be a finite Decimal")
        for name, value in (("periods", self.periods), ("periods_per_year", self.periods_per_year)):
            if type(value) is not int:
                raise AnnualizationError(f"{name} must be an int")
        if self.periods_per_year < 1:
            raise AnnualizationError("periods_per_year must be at least 1")
        if self.periods < 0:
            raise AnnualizationError("periods must be non-negative")
        if self.cagr is not None and (not isinstance(self.cagr, Decimal) or not self.cagr.is_finite()):
            raise AnnualizationError("cagr must be a finite Decimal or None")


def compute_cagr(
    *,
    beginning_value: Decimal,
    ending_value: Decimal,
    periods: int,
    periods_per_year: int,
) -> CagrResult:
    """Compute the compound annual growth rate (pure, deterministic).

    Returns ``CagrResult.cagr == None`` when ``periods <= 0`` (insufficient
    duration — undefined, never zero). Raises :class:`AnnualizationError` for
    non-positive capital or an invalid annualization basis.
    """
    for name, value in (("beginning_value", beginning_value), ("ending_value", ending_value)):
        if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
            raise AnnualizationError(f"{name} must be a positive finite Decimal")
    if type(periods) is not int:
        raise AnnualizationError("periods must be an int")
    if periods < 0:
        raise AnnualizationError("periods must be non-negative")
    if type(periods_per_year) is not int:
        raise AnnualizationError("periods_per_year must be an int")
    if periods_per_year < 1:
        raise AnnualizationError("periods_per_year must be at least 1")

    with localcontext() as ctx:
        ctx.prec = DECIMAL_PRECISION
        ratio = ending_value / beginning_value
        total_return = ratio - Decimal(1)
        if periods <= 0:
            cagr: Decimal | None = None
        else:
            exponent = Decimal(periods_per_year) / Decimal(periods)
            cagr = (ratio.ln() * exponent).exp() - Decimal(1)

    return CagrResult(
        beginning_value=beginning_value,
        ending_value=ending_value,
        total_return=total_return,
        periods=periods,
        periods_per_year=periods_per_year,
        cagr=cagr,
    )
