"""Phase 5 Signal ORM model schema (columns + uniqueness + nullable FKs)."""

from __future__ import annotations

from sqlalchemy import UniqueConstraint

from alpha_algo_shared.db.models import Signal


def test_signal_model_has_phase5_provenance_columns() -> None:
    cols = {c.name for c in Signal.__table__.columns}
    for name in (
        "signal_id",
        "identity_key",
        "content_hash",
        "strategy_id",
        "strategy_version",
        "config_hash",
        "code_hash",
        "run_id",
        "state",
        "processed_at",
    ):
        assert name in cols, f"missing column: {name}"


def test_signal_model_has_idempotency_unique_constraints() -> None:
    uq_cols: set[str] = set()
    for constraint in Signal.__table__.constraints:
        if isinstance(constraint, UniqueConstraint):
            for col in constraint.columns:
                uq_cols.add(col.name)
    assert "signal_id" in uq_cols
    assert "identity_key" in uq_cols


def test_signal_relational_fks_are_nullable() -> None:
    cols = Signal.__table__.columns
    assert cols["strategy_run_id"].nullable is True
    assert cols["strategy_version_id"].nullable is True


def test_signal_no_sensitive_secret_columns() -> None:
    cols = {c.name for c in Signal.__table__.columns}
    for secret in ("api_key", "secret", "password", "token", "credential"):
        assert secret not in cols
