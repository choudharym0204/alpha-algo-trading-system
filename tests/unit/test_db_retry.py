from __future__ import annotations

import pytest
from sqlalchemy.exc import OperationalError

import alpha_algo_api.db as db


def _operational_error() -> OperationalError:
    return OperationalError("SELECT 1", {}, Exception("connection refused"))


def test_retry_succeeds_after_transient_failures() -> None:
    state = {"calls": 0}

    def flaky() -> str:
        state["calls"] += 1
        if state["calls"] < 3:
            raise _operational_error()
        return "ok"

    assert db.run_with_retry(flaky, attempts=3, delay_seconds=0) == "ok"
    assert state["calls"] == 3


def test_retry_raises_after_exhausting_attempts() -> None:
    state = {"calls": 0}

    def always_fail() -> None:
        state["calls"] += 1
        raise _operational_error()

    with pytest.raises(OperationalError):
        db.run_with_retry(always_fail, attempts=2, delay_seconds=0)
    assert state["calls"] == 2


def test_retry_does_not_retry_non_retryable_errors() -> None:
    state = {"calls": 0}

    def boom() -> None:
        state["calls"] += 1
        raise ValueError("not a connection error")

    with pytest.raises(ValueError):
        db.run_with_retry(boom, attempts=3, delay_seconds=0)
    assert state["calls"] == 1


def test_retry_passes_args_and_kwargs() -> None:
    def add(a: int, b: int) -> int:
        return a + b

    assert db.run_with_retry(add, 1, b=2, attempts=1, delay_seconds=0) == 3
