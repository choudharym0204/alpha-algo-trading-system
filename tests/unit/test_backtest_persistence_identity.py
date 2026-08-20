from __future__ import annotations

from decimal import Decimal

import pytest

from alpha_algo_backtest_persistence import (
    BacktestRunIdentity,
    PersistenceError,
    identity_sha256,
    run_id_for_identity,
)
from tests.unit.backtest_p16_test_support import utc


def _identity(**overrides) -> BacktestRunIdentity:
    base = dict(
        dataset_id="ds",
        source="unit",
        input_sha256="a" * 64,
    )
    base.update(overrides)
    return BacktestRunIdentity(**base)


class TestIdentity:
    def test_same_inputs_same_identity(self) -> None:
        a = _identity(seed="s", initial_capital=Decimal("1000"))
        b = _identity(seed="s", initial_capital=Decimal("1000"))
        assert identity_sha256(a) == identity_sha256(b)
        assert a.run_id() == b.run_id()

    def test_seed_is_part_of_identity(self) -> None:
        a = _identity(seed="s1")
        b = _identity(seed="s2")
        assert identity_sha256(a) != identity_sha256(b)

    def test_cost_model_is_part_of_identity(self) -> None:
        a = _identity(commission_per_fill=Decimal("1"))
        b = _identity(commission_per_fill=Decimal("2"))
        assert identity_sha256(a) != identity_sha256(b)

    def test_wall_clock_not_part_of_identity(self) -> None:
        # start_at/end_at are period boundaries (immutable inputs), but the
        # audit created_at is not a field; nothing wall-clock can be passed.
        a = _identity(start_at=utc(2026, 1, 1), end_at=utc(2026, 2, 1))
        b = _identity(start_at=utc(2026, 1, 1), end_at=utc(2026, 2, 1))
        assert identity_sha256(a) == identity_sha256(b)

    def test_start_end_are_part_of_identity(self) -> None:
        a = _identity(start_at=utc(2026, 1, 1), end_at=utc(2026, 2, 1))
        b = _identity(start_at=utc(2026, 1, 2), end_at=utc(2026, 2, 1))
        assert identity_sha256(a) != identity_sha256(b)

    def test_instrument_universe_is_order_stable(self) -> None:
        a = _identity(instrument_universe=("B", "A"))
        b = _identity(instrument_universe=("A", "B"))
        assert identity_sha256(a) == identity_sha256(b)

    def test_run_id_is_stable_uuid(self) -> None:
        a = _identity()
        assert a.run_id() == a.run_id()
        assert run_id_for_identity(a.canonical_string()) == a.run_id()

    def test_empty_required_field_rejected(self) -> None:
        with pytest.raises(PersistenceError):
            BacktestRunIdentity(dataset_id="", source="unit", input_sha256="a" * 64)

    def test_bad_input_hash_rejected(self) -> None:
        with pytest.raises(PersistenceError):
            _identity(input_sha256="short")

    def test_negative_capital_rejected(self) -> None:
        with pytest.raises(PersistenceError):
            _identity(initial_capital=Decimal("-1"))

    def test_digest_is_64_hex(self) -> None:
        digest = identity_sha256(_identity())
        assert len(digest) == 64
        int(digest, 16)  # hex-parseable
