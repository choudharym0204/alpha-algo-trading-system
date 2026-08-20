"""Historical-data quality validation for the backtesting subsystem (Phase 16).

Observational classification of a raw record sequence into valid /
quarantined / rejected buckets. No silent repair, no reorder, no dedup, no
interpolation. Injected (never wall-clock) reference time and expected step
control future-dated and gap detection.

Safety boundaries: pure functions, no network, no broker, no I/O, isolated
from LIVE/PAPER.
"""

from alpha_algo_backtest_quality.errors import DataQualityError
from alpha_algo_backtest_quality.validation import (
    DATA_QUALITY_POLICY,
    DataQualityFinding,
    DataQualityReport,
    QualityClass,
    validate_dataset,
)

__all__ = [
    "DATA_QUALITY_POLICY",
    "DataQualityError",
    "DataQualityFinding",
    "DataQualityReport",
    "QualityClass",
    "validate_dataset",
]
