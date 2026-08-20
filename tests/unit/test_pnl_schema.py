"""Phase 13 — P&L schema tests."""

from __future__ import annotations

from pathlib import Path

from alpha_algo_shared.db.models.pnl import PnlEvent, PnlSnapshot


def test_pnl_event_columns():
    cols = set(PnlEvent.__table__.columns.keys())
    for name in (
        "execution_id", "event_type", "account_id", "strategy_run_id", "instrument_id",
        "position_id", "trading_mode", "side", "quantity", "price", "average_cost",
        "gross_pnl", "costs", "net_pnl", "occurred_at", "content_hash",
    ):
        assert name in cols, f"missing pnl_events column {name}"


def test_pnl_event_unique_constraint():
    names = {c.name for c in PnlEvent.__table__.constraints}
    assert "uq_pnl_events_execution_id" in names


def test_pnl_snapshot_columns():
    cols = set(PnlSnapshot.__table__.columns.keys())
    for name in (
        "account_id", "strategy_run_id", "trading_mode", "snapshot_at",
        "realized_pnl", "unrealized_pnl", "gross_pnl", "costs", "net_pnl",
        "position_count", "status",
    ):
        assert name in cols, f"missing pnl_snapshots column {name}"


def test_pnl_snapshot_unique_constraint_and_index():
    names = {c.name for c in PnlSnapshot.__table__.constraints}
    assert "uq_pnl_snapshots_account_mode_snapshot_at" in names
    index_names = {ix.name for ix in PnlSnapshot.__table__.indexes}
    assert "ix_pnl_snapshots_account_mode" in index_names


def test_migration_revision_chain_is_correct():
    migration = Path(__file__).resolve().parents[2] / "migrations" / "versions" / "20260820_pnl_engine.py"
    text = migration.read_text(encoding="utf-8")
    assert 'revision = "20260820_pnl_engine"' in text
    assert 'down_revision = "20260820_portfolio_engine"' in text
    assert "pnl_events" in text
    assert "pnl_snapshots" in text
