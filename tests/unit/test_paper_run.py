from __future__ import annotations

from datetime import UTC, datetime

import pytest

from alpha_algo_paper_runtime import (
    PaperRun,
    PaperRunStatus,
    compute_config_hash,
    new_paper_run_id,
)

from paper_test_support import make_run


def test_seeded_run_id_is_deterministic() -> None:
    assert new_paper_run_id("alpha-run-1") == new_paper_run_id("alpha-run-1")


def test_unseeded_run_id_is_unique() -> None:
    assert new_paper_run_id() != new_paper_run_id()


def test_seeded_and_unseeded_differ() -> None:
    assert new_paper_run_id("alpha-run-1") != new_paper_run_id()


def test_config_hash_is_deterministic() -> None:
    a = compute_config_hash({"seed": "1", "slippage": "ZERO"})
    b = compute_config_hash({"seed": "1", "slippage": "ZERO"})
    assert a == b


def test_config_hash_is_order_independent() -> None:
    a = compute_config_hash({"seed": "1", "slippage": "ZERO"})
    b = compute_config_hash({"slippage": "ZERO", "seed": "1"})
    assert a == b


def test_config_hash_differs_for_different_config() -> None:
    assert compute_config_hash({"seed": "1"}) != compute_config_hash({"seed": "2"})


def test_empty_config_has_stable_hash() -> None:
    assert compute_config_hash() == compute_config_hash({})


def test_run_requires_config_hash() -> None:
    with pytest.raises(ValueError, match="config_hash"):
        PaperRun(
            paper_run_id=new_paper_run_id(),
            status=PaperRunStatus.ACTIVE,
            config_hash="",
            created_at=datetime(2026, 3, 1, tzinfo=UTC),
        )


def test_run_defaults() -> None:
    run = make_run()
    assert run.status is PaperRunStatus.ACTIVE
    assert run.completed_at is None
