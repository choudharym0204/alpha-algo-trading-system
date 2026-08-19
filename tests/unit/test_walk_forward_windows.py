from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest
from dataclasses import FrozenInstanceError

from alpha_algo_contracts import MarketTick
from alpha_algo_backtesting import BacktestInput
from alpha_algo_backtest_engine import BacktestRun
from alpha_algo_walk_forward import (
    WINDOW_SCHEDULE_POLICY,
    WalkForwardConfig,
    WalkForwardError,
    WalkForwardWindow,
    WindowSlice,
    build_windows,
)

INSTRUMENT = UUID("00000000-0000-0000-0000-000000000001")
UTC = timezone.utc


def utc(y, mo, d, h=9, mi=0, s=0) -> datetime:
    return datetime(y, mo, d, h, mi, s, tzinfo=UTC)


def tick(ts: datetime, ltp: str = "100", bid: str = "99.5", ask: str = "100.5") -> MarketTick:
    return MarketTick(
        instrument_id=INSTRUMENT,
        exchange="NSE",
        symbol="TEST",
        timestamp=ts,
        ltp=Decimal(ltp),
        bid=Decimal(bid),
        ask=Decimal(ask),
        source_broker="unit",
        source_sequence=f"seq-{ts.isoformat()}",
        received_at=ts,
    )


def canonical_input() -> BacktestInput:
    records = tuple(tick(utc(2026, 1, 2, 9, 0) + timedelta(minutes=i)) for i in range(100))
    return BacktestInput(dataset_id="ds", source="unit", records=records)


CANONICAL_CONFIG = WalkForwardConfig(training_records=20, validation_records=20, test_records=20, step_records=20)


def config_of(train: int, val: int, test: int, step: int) -> WalkForwardConfig:
    return WalkForwardConfig(training_records=train, validation_records=val, test_records=test, step_records=step)


class TestCanonicalWindows:
    def test_window_count_and_start_indices(self) -> None:
        windows = build_windows(inputs=canonical_input(), config=CANONICAL_CONFIG)
        assert len(windows) == 3
        assert [w.index for w in windows] == [0, 1, 2]
        assert [w.train.start_index for w in windows] == [0, 20, 40]

    def test_exact_slice_boundaries(self) -> None:
        windows = build_windows(inputs=canonical_input(), config=CANONICAL_CONFIG)
        expected = [(0, 20, 20, 40, 40, 60), (20, 40, 40, 60, 60, 80), (40, 60, 60, 80, 80, 100)]
        for window, (ts, te, vs, ve, es, ee) in zip(windows, expected):
            assert (window.train.start_index, window.train.end_index) == (ts, te)
            assert (window.validation.start_index, window.validation.end_index) == (vs, ve)
            assert (window.test.start_index, window.test.end_index) == (es, ee)

    def test_intra_window_disjointness(self) -> None:
        windows = build_windows(inputs=canonical_input(), config=CANONICAL_CONFIG)
        for window in windows:
            train = set(range(window.train.start_index, window.train.end_index))
            validation = set(range(window.validation.start_index, window.validation.end_index))
            test = set(range(window.test.start_index, window.test.end_index))
            assert train.isdisjoint(validation)
            assert validation.isdisjoint(test)
            assert train.isdisjoint(test)
            assert max(train) < min(validation)
            assert max(validation) < min(test)

    def test_slices_contiguous_within_window(self) -> None:
        windows = build_windows(inputs=canonical_input(), config=CANONICAL_CONFIG)
        for window in windows:
            assert window.train.end_index == window.validation.start_index
            assert window.validation.end_index == window.test.start_index

    def test_in_order_no_lookahead(self) -> None:
        windows = build_windows(inputs=canonical_input(), config=CANONICAL_CONFIG)
        for window in windows:
            assert window.train.start_timestamp < window.validation.end_timestamp < window.test.end_timestamp
        for k in range(1, len(windows)):
            assert windows[k].test.start_index > windows[k - 1].test.start_index
        assert windows[-1].test.start_timestamp > windows[0].validation.end_timestamp

    def test_record_slices_reference_caller_data(self) -> None:
        inputs = canonical_input()
        windows = build_windows(inputs=inputs, config=CANONICAL_CONFIG)
        assert windows[0].train_input.records[0] is inputs.records[0]
        assert windows[0].train_input.records[-1] is inputs.records[19]
        assert windows[2].test_input.records[-1] is inputs.records[99]
        # Slices are fresh validated inputs with their own manifest hashes.
        assert windows[0].train_input.content_sha256 != inputs.content_sha256
        assert windows[0].train_input.dataset_id == inputs.dataset_id

    def test_timestamp_boundaries_exact(self) -> None:
        windows = build_windows(inputs=canonical_input(), config=CANONICAL_CONFIG)
        w0 = windows[0]
        assert (w0.train.start_timestamp, w0.train.end_timestamp) == (utc(2026, 1, 2, 9, 0), utc(2026, 1, 2, 9, 19))
        assert (w0.validation.start_timestamp, w0.validation.end_timestamp) == (utc(2026, 1, 2, 9, 20), utc(2026, 1, 2, 9, 39))
        assert (w0.test.start_timestamp, w0.test.end_timestamp) == (utc(2026, 1, 2, 9, 40), utc(2026, 1, 2, 9, 59))
        assert windows[1].test.start_timestamp == utc(2026, 1, 2, 10, 0)
        assert windows[2].test.end_timestamp == utc(2026, 1, 2, 10, 39)

    def test_last_window_ends_at_dataset_end(self) -> None:
        inputs = canonical_input()
        windows = build_windows(inputs=inputs, config=CANONICAL_CONFIG)
        assert windows[2].test.end_index == inputs.record_count
        assert windows[2].test.end_timestamp == inputs.last_timestamp

    def test_window_is_frozen(self) -> None:
        windows = build_windows(inputs=canonical_input(), config=CANONICAL_CONFIG)
        with pytest.raises(FrozenInstanceError):
            windows[0].index = 99  # type: ignore[misc]

    def test_cross_window_overlap_is_legal(self) -> None:
        windows = build_windows(inputs=canonical_input(), config=CANONICAL_CONFIG)
        # W1.train re-covers W0.val records (rolling retrain) - legal and intended.
        assert windows[1].train.start_index == windows[0].validation.start_index
        assert windows[1].train.end_index == windows[0].validation.end_index
        # Only within-window disjointness is required.
        assert windows[0].test.start_index == windows[1].train.start_index + 20

    def test_in_sample_union(self) -> None:
        inputs = canonical_input()
        windows = build_windows(inputs=inputs, config=CANONICAL_CONFIG)
        w0 = windows[0]
        assert w0.in_sample == WindowSlice(
            start_index=0,
            end_index=40,
            start_timestamp=utc(2026, 1, 2, 9, 0),
            end_timestamp=utc(2026, 1, 2, 9, 39),
        )
        assert w0.in_sample_input.record_count == 40
        assert w0.in_sample_input.records[0] is inputs.records[0]
        assert w0.in_sample_input.records[-1] is inputs.records[39]


class TestStepSemantics:
    def test_step_one_sliding_windows(self) -> None:
        config = config_of(10, 5, 1, 1)
        windows = build_windows(inputs=canonical_input(), config=config)
        assert len(windows) == 85  # (100 - 16) // 1 + 1
        assert [w.train.start_index for w in windows] == list(range(0, 85))
        assert windows[84].test.end_index == 100

    def test_step_equals_test_length_tiles(self) -> None:
        config = config_of(10, 5, 5, 5)
        windows = build_windows(inputs=canonical_input(), config=config)
        assert len(windows) == 17  # (100 - 20) // 5 + 1
        for k, window in enumerate(windows):
            assert (window.test.start_index, window.test.end_index) == (15 + 5 * k, 20 + 5 * k)

    def test_step_equals_span_tiles(self) -> None:
        config = config_of(10, 5, 5, 20)
        windows = build_windows(inputs=canonical_input(), config=config)
        assert len(windows) == 5
        assert [w.train.start_index for w in windows] == [0, 20, 40, 60, 80]

    def test_step_below_span_rolling_overlap(self) -> None:
        config = config_of(10, 5, 5, 15)
        windows = build_windows(inputs=canonical_input(), config=config)
        assert len(windows) == 6
        assert [w.train.start_index for w in windows] == [0, 15, 30, 45, 60, 75]
        # Records in no window exist (gap semantics) - visible via coverage metadata at run time.
        assert windows[0].test.end_index == 20
        assert windows[1].train.start_index == 15

    def test_step_exceeds_span_leaves_gaps(self) -> None:
        # True gap semantics: step > span -> records belonging to NO window.
        config = config_of(5, 5, 10, 25)
        windows = build_windows(inputs=canonical_input(), config=config)
        assert len(windows) == 4  # (100 - 20) // 25 + 1
        assert [w.train.start_index for w in windows] == [0, 25, 50, 75]
        assert [w.test.end_index for w in windows] == [20, 45, 70, 95]
        covered = set()
        for window in windows:
            covered.update(range(window.train.start_index, window.test.end_index))
        for start, end in ((20, 25), (45, 50), (70, 75), (95, 100)):
            assert set(range(start, end)).isdisjoint(covered)


class TestTrailingShortfall:
    def test_span_exactly_matches_dataset(self) -> None:
        config = config_of(40, 30, 30, 30)
        windows = build_windows(inputs=canonical_input(), config=config)
        assert len(windows) == 1
        assert windows[0].train.start_index == 0
        assert windows[0].test.end_index == 100

    def test_span_exceeds_dataset_rejected(self) -> None:
        config = config_of(40, 30, 31, 31)
        with pytest.raises(WalkForwardError, match="cannot form a single full window"):
            build_windows(inputs=canonical_input(), config=config)

    def test_trailing_remainder_unused_not_error(self) -> None:
        # N=100, span=60, step=25: windows at starts 0 and 25; records [85,100) are
        # outside the schedule (unused, never truncated) and reported via coverage.
        config = config_of(20, 20, 20, 25)
        windows = build_windows(inputs=canonical_input(), config=config)
        assert len(windows) == 2
        assert [w.train.start_index for w in windows] == [0, 25]
        assert windows[1].test.end_index == 85


class TestConfigValidation:
    def test_zero_train_rejected(self) -> None:
        with pytest.raises(WalkForwardError, match="training_records"):
            config_of(0, 5, 5, 5)

    def test_zero_validation_rejected(self) -> None:
        with pytest.raises(WalkForwardError, match="validation_records"):
            config_of(10, 0, 5, 5)

    def test_zero_test_rejected(self) -> None:
        with pytest.raises(WalkForwardError, match="test_records"):
            config_of(10, 5, 0, 5)

    def test_zero_step_rejected(self) -> None:
        with pytest.raises(WalkForwardError, match="step_records"):
            config_of(10, 5, 5, 0)

    def test_negative_step_rejected(self) -> None:
        with pytest.raises(WalkForwardError, match="step_records"):
            config_of(10, 5, 5, -5)

    def test_step_below_test_length_rejected(self) -> None:
        # Overlapping out-of-sample windows would break period independence.
        with pytest.raises(WalkForwardError, match="step_records must be >= test_records"):
            config_of(10, 5, 10, 5)

    def test_non_integer_config_rejected(self) -> None:
        with pytest.raises(WalkForwardError, match="training_records"):
            config_of(20.5, 5, 5, 5)
        with pytest.raises(WalkForwardError, match="step_records"):
            config_of(10, 5, 5, "20")

    def test_bool_config_rejected(self) -> None:
        with pytest.raises(WalkForwardError, match="training_records"):
            config_of(True, 5, 5, 5)

    def test_missing_config_rejected(self) -> None:
        with pytest.raises(TypeError):
            WalkForwardConfig()  # type: ignore[call-arg]

    def test_config_is_frozen(self) -> None:
        config = config_of(10, 5, 5, 5)
        with pytest.raises(FrozenInstanceError):
            config.training_records = 99  # type: ignore[misc]

    def test_minimal_config_accepted(self) -> None:
        inputs = canonical_input()
        config = config_of(1, 1, 1, 1)
        windows = build_windows(inputs=inputs, config=config)
        assert len(windows) == 98  # (100 - 3) // 1 + 1

    def test_builder_rejects_non_backtest_input(self) -> None:
        with pytest.raises(WalkForwardError, match="inputs must be a BacktestInput"):
            build_windows(inputs="nope", config=CANONICAL_CONFIG)

    def test_builder_rejects_non_config(self) -> None:
        with pytest.raises(WalkForwardError, match="config must be a WalkForwardConfig"):
            build_windows(inputs=canonical_input(), config={"train": 10})  # type: ignore[arg-type]


class TestWindowValidation:
    def test_window_rejects_incoherent_slices(self) -> None:
        inputs = canonical_input()
        windows = build_windows(inputs=inputs, config=CANONICAL_CONFIG)
        base = windows[0]
        with pytest.raises(WalkForwardError, match="contiguous"):
            WalkForwardWindow(
                index=base.index,
                train=base.train,
                validation=WindowSlice(
                    start_index=base.validation.start_index + 1,
                    end_index=base.validation.end_index,
                    start_timestamp=base.validation.start_timestamp,
                    end_timestamp=base.validation.end_timestamp,
                ),
                test=base.test,
                train_input=base.train_input,
                validation_input=base.validation_input,
                test_input=base.test_input,
            )

    def test_window_rejects_input_slice_mismatch(self) -> None:
        inputs = canonical_input()
        windows = build_windows(inputs=inputs, config=CANONICAL_CONFIG)
        base = windows[0]
        wrong_input = BacktestInput(
            dataset_id="ds",
            source="unit",
            records=inputs.records[0:10],  # 10 records, but the test slice spans 20
        )
        with pytest.raises(WalkForwardError, match="record count does not match"):
            WalkForwardWindow(
                index=base.index,
                train=base.train,
                validation=base.validation,
                test=base.test,
                train_input=base.train_input,
                validation_input=base.validation_input,
                test_input=wrong_input,
            )

    def test_window_rejects_bad_timestamp_order(self) -> None:
        inputs = canonical_input()
        windows = build_windows(inputs=inputs, config=CANONICAL_CONFIG)
        base = windows[0]
        with pytest.raises(WalkForwardError, match="strictly increasing"):
            WalkForwardWindow(
                index=base.index,
                train=base.train,
                validation=base.validation,
                test=WindowSlice(
                    start_index=base.test.start_index,
                    end_index=base.test.end_index,
                    start_timestamp=utc(2026, 1, 2, 9, 30),
                    end_timestamp=utc(2026, 1, 2, 9, 35),
                ),
                train_input=base.train_input,
                validation_input=base.validation_input,
                test_input=base.test_input,
            )

    def test_policy_constant_is_fixed_and_exported(self) -> None:
        assert isinstance(WINDOW_SCHEDULE_POLICY, str)
        assert "never overlap" in WINDOW_SCHEDULE_POLICY
        assert "trailing remainder" in WINDOW_SCHEDULE_POLICY

    def test_window_types_are_clean(self) -> None:
        # BacktestRun passed where a config is expected is refused at the builder.
        inputs = canonical_input()
        with pytest.raises(WalkForwardError):
            build_windows(inputs=inputs, config=BacktestRun)  # type: ignore[arg-type]
