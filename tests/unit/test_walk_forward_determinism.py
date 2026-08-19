from __future__ import annotations

import os
import random
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from alpha_algo_contracts import MarketTick
from alpha_algo_backtesting import BacktestInput
from alpha_algo_backtest_engine import (
    CostModel,
    IntentSide,
    IntentType,
    OrderIntent,
    compute_metrics,
    run_backtest,
)
from alpha_algo_walk_forward import (
    WalkForwardConfig,
    WindowBacktestResult,
    aggregate_periods,
    assess_overfitting,
    build_windows,
    run_walk_forward,
)

INSTRUMENT = UUID("00000000-0000-0000-0000-000000000001")
UTC = timezone.utc


def utc(y, mo, d, h=9, mi=0, s=0) -> datetime:
    return datetime(y, mo, d, h, mi, s, tzinfo=UTC)


def tick(ts: datetime, ltp: str, bid: str, ask: str) -> MarketTick:
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


def demo_input(metadata=None) -> BacktestInput:
    records = tuple(
        tick(
            utc(2026, 1, 2, 9, 0) + timedelta(minutes=i),
            str(100 + 2 * i),
            str(100 + 2 * i - 0.5),
            str(100 + 2 * i + 0.5),
        )
        for i in range(40)
    )
    return BacktestInput(dataset_id="ds", source="unit", records=records, metadata=metadata or {})


DEMO_CONFIG = WalkForwardConfig(training_records=10, validation_records=5, test_records=5, step_records=10)


def slice_metrics(slice_input: BacktestInput):
    first = slice_input.first_timestamp
    buy = OrderIntent(
        side=IntentSide.BUY,
        order_type=IntentType.MARKET,
        quantity=Decimal("10"),
        decided_at=first - timedelta(seconds=30),
    )
    sell = OrderIntent(
        side=IntentSide.SELL,
        order_type=IntentType.MARKET,
        quantity=Decimal("10"),
        decided_at=first + timedelta(seconds=20),
    )
    run = run_backtest(
        inputs=slice_input,
        intents=(buy, sell),
        cost_model=CostModel(Decimal("0"), Decimal("0")),
        initial_capital=Decimal("100000"),
    )
    return compute_metrics(run, risk_free_rate_per_period=Decimal("0"))


def demo_runner(window):
    return WindowBacktestResult(
        window=window,
        is_metrics=slice_metrics(window.in_sample_input),
        oos_metrics=slice_metrics(window.test_input),
    )


def full_pipeline(inputs: BacktestInput, config: WalkForwardConfig):
    result = run_walk_forward(inputs=inputs, config=config, window_runner=demo_runner)
    assessment = assess_overfitting(periods=result.periods, aggregate=result.aggregate)
    return result, assessment


class TestDeterminism:
    def test_identical_inputs_identical_pipeline(self) -> None:
        first_result, first_assessment = full_pipeline(demo_input(), DEMO_CONFIG)
        second_result, second_assessment = full_pipeline(demo_input(), DEMO_CONFIG)
        assert second_result == first_result
        assert second_assessment == first_assessment
        assert second_result.aggregate == first_result.aggregate
        assert [w.index for w in second_result.windows] == [w.index for w in first_result.windows]

    def test_no_cross_run_state(self) -> None:
        first = run_walk_forward(inputs=demo_input(), config=DEMO_CONFIG, window_runner=demo_runner)
        other_config = WalkForwardConfig(training_records=10, validation_records=5, test_records=5, step_records=10)
        run_walk_forward(inputs=demo_input(), config=other_config, window_runner=demo_runner)
        second = run_walk_forward(inputs=demo_input(), config=DEMO_CONFIG, window_runner=demo_runner)
        assert second == first

    def test_wall_clock_and_random_never_consulted(self, monkeypatch) -> None:
        # The AST structural test already proves zero datetime.now/time.*/random.*
        # sites in the package source (and datetime's now/utcnow are classmethods
        # of an immutable C type, so they cannot be patched on Python 3.13). This
        # runtime probe patches the global time/random modules to RAISE: if the
        # pipeline (or anything it transitively calls) consulted them, it would
        # fail loudly instead of silently returning a fake value.
        def _raise(*_args, **_kwargs):
            raise AssertionError("time/random consulted")

        for name in ("time", "monotonic", "perf_counter", "sleep"):
            monkeypatch.setattr(time, name, _raise)
        for name in ("random", "uniform", "randint", "choice", "shuffle", "sample"):
            monkeypatch.setattr(random, name, _raise)

        patched_result, patched_assessment = full_pipeline(demo_input(), DEMO_CONFIG)
        clean_result, clean_assessment = full_pipeline(demo_input(), DEMO_CONFIG)
        assert patched_result == clean_result
        assert patched_assessment == clean_assessment

    def test_input_metadata_does_not_affect_results(self) -> None:
        # Metadata is echoed onto sliced inputs (self-describing provenance), so
        # window objects differ by metadata; the COMPUTED artifacts must not.
        plain = full_pipeline(demo_input(), DEMO_CONFIG)
        decorated = full_pipeline(demo_input(metadata={"anything": "goes", "nested": [1, 2, 3]}), DEMO_CONFIG)
        assert decorated[0].input_sha256 == plain[0].input_sha256
        assert decorated[0].aggregate == plain[0].aggregate
        assert decorated[1] == plain[1]
        for plain_period, decorated_period in zip(plain[0].periods, decorated[0].periods):
            assert plain_period.is_metrics == decorated_period.is_metrics
            assert plain_period.oos_metrics == decorated_period.oos_metrics
            assert plain_period.window.train_input.records == decorated_period.window.train_input.records

    def test_build_windows_pure(self) -> None:
        inputs = demo_input()
        first = build_windows(inputs=inputs, config=DEMO_CONFIG)
        second = build_windows(inputs=inputs, config=DEMO_CONFIG)
        assert first == second
        assert all(a == b for a, b in zip(first, second))

    def test_full_walk_forward_suite_passes_under_different_hash_seeds(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        files = [
            repo_root / "tests" / "unit" / "test_walk_forward_windows.py",
            repo_root / "tests" / "unit" / "test_walk_forward_runner.py",
            repo_root / "tests" / "unit" / "test_walk_forward_aggregate.py",
            repo_root / "tests" / "unit" / "test_walk_forward_overfitting.py",
            repo_root / "tests" / "unit" / "test_walk_forward_no_live_access.py",
        ]
        env = dict(os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONHASHSEED"] = "1"
        first_run = subprocess.run(
            [sys.executable, "-m", "pytest", *[str(path) for path in files], "-p", "no:cacheprovider", "-q"],
            capture_output=True,
            text=True,
            env=env,
            timeout=180,
        )
        env["PYTHONHASHSEED"] = "999"
        second_run = subprocess.run(
            [sys.executable, "-m", "pytest", *[str(path) for path in files], "-p", "no:cacheprovider", "-q"],
            capture_output=True,
            text=True,
            env=env,
            timeout=180,
        )
        for run in (first_run, second_run):
            assert run.returncode == 0, (
                f"walk-forward suite failed under PYTHONHASHSEED={env['PYTHONHASHSEED']}\n"
                f"stdout tail:\n{run.stdout[-2000:]}\nstderr tail:\n{run.stderr[-2000:]}"
            )
