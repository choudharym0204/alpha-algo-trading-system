from __future__ import annotations

from datetime import timedelta

import pytest

from alpha_algo_backtest_quality import (
    DataQualityError,
    QualityClass,
    validate_dataset,
)
from tests.unit.backtest_p16_test_support import tick, utc


class TestDataQuality:
    def test_clean_series_is_valid(self) -> None:
        records = (
            tick(utc(2026, 1, 1, 9, 0), "100"),
            tick(utc(2026, 1, 1, 9, 1), "101"),
            tick(utc(2026, 1, 1, 9, 2), "102"),
        )
        report = validate_dataset(records)
        assert report.dataset_classification is QualityClass.VALID
        assert report.valid_count == 3
        assert report.is_simulation_ready

    def test_out_of_order_is_rejected(self) -> None:
        records = (
            tick(utc(2026, 1, 1, 9, 1), "101"),
            tick(utc(2026, 1, 1, 9, 0), "100"),
        )
        report = validate_dataset(records)
        assert report.dataset_classification is QualityClass.REJECTED
        assert report.rejected_count == 1

    def test_duplicate_timestamp_is_quarantined(self) -> None:
        records = (
            tick(utc(2026, 1, 1, 9, 0), "100"),
            tick(utc(2026, 1, 1, 9, 0), "100"),
        )
        report = validate_dataset(records)
        assert report.dataset_classification is QualityClass.QUARANTINED
        assert report.quarantined_count == 1

    def test_future_record_is_quarantined(self) -> None:
        records = (
            tick(utc(2026, 1, 1, 9, 0), "100"),
            tick(utc(2026, 1, 1, 9, 1), "101"),
        )
        report = validate_dataset(records, reference_time=utc(2026, 1, 1, 9, 0, 30))
        assert report.dataset_classification is QualityClass.QUARANTINED
        assert any("future-dated" in f.reason for f in report.findings)

    def test_gap_is_quarantined(self) -> None:
        records = (
            tick(utc(2026, 1, 1, 9, 0), "100"),
            tick(utc(2026, 1, 1, 9, 30), "101"),
        )
        report = validate_dataset(records, expected_step=timedelta(minutes=1), gap_multiple=3)
        assert report.dataset_classification is QualityClass.QUARANTINED
        assert any("gap" in f.reason for f in report.findings)

    def test_rejected_outranks_quarantined(self) -> None:
        # Duplicate (quarantined) AND a future-dated record but also a bad tick.
        bad = tick(utc(2026, 1, 1, 9, 1), "100", bid="105", ask="100")  # bid > ask
        records = (tick(utc(2026, 1, 1, 9, 0), "100"), bad)
        report = validate_dataset(records)
        assert report.dataset_classification is QualityClass.REJECTED

    def test_invalid_call_rejected(self) -> None:
        with pytest.raises(DataQualityError):
            validate_dataset(("not", "records"))  # type: ignore[arg-type]
        with pytest.raises(DataQualityError):
            validate_dataset((), expected_step=timedelta(0))

    def test_empty_is_valid(self) -> None:
        report = validate_dataset(())
        assert report.total_records == 0
        assert report.dataset_classification is QualityClass.VALID
