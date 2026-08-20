"""Phase 12 — portfolio snapshot schema tests."""

from __future__ import annotations

from pathlib import Path

from alpha_algo_shared.db.models.safety import PortfolioSnapshot


def _columns():
    return set(PortfolioSnapshot.__table__.columns.keys())


def test_portfolio_snapshot_has_aggregate_columns():
    cols = _columns()
    for name in (
        "market_value",
        "gross_exposure",
        "net_exposure",
        "long_exposure",
        "short_exposure",
        "position_count",
        "available_margin",
        "used_margin",
        "status",
        "snapshot_payload",
    ):
        assert name in cols, f"missing column {name}"


def test_portfolio_snapshot_unique_constraint_present():
    names = {c.name for c in PortfolioSnapshot.__table__.constraints}
    assert "uq_portfolio_snapshots_account_mode_snapshot_at" in names


def test_portfolio_snapshot_account_mode_index_present():
    index_names = {ix.name for ix in PortfolioSnapshot.__table__.indexes}
    assert "ix_portfolio_snapshots_account_mode" in index_names


def test_migration_revision_chain_is_correct():
    migration = Path(__file__).resolve().parents[2] / "migrations" / "versions" / "20260820_portfolio_engine.py"
    text = migration.read_text(encoding="utf-8")
    assert 'revision = "20260820_portfolio_engine"' in text
    assert 'down_revision = "20260820_position_engine"' in text
    # New aggregate columns must be present in the migration.
    for col in ("market_value", "gross_exposure", "net_exposure", "long_exposure", "short_exposure", "position_count", "available_margin", "used_margin", "status"):
        assert col in text, f"migration missing {col}"
