"""Phase 15 — paper persistence schema tests."""

from __future__ import annotations

from pathlib import Path

from alpha_algo_shared.db.models.paper import PaperAccount, PaperFunds, PaperRun


def test_paper_run_columns():
    cols = set(PaperRun.__table__.columns.keys())
    for name in ("config_hash", "status", "started_at", "completed_at"):
        assert name in cols, f"missing paper_runs column {name}"


def test_paper_account_columns_and_fk():
    cols = set(PaperAccount.__table__.columns.keys())
    for name in ("paper_run_id", "trading_mode", "starting_capital", "status", "reset_at"):
        assert name in cols, f"missing paper_accounts column {name}"
    fks = {fk.target_fullname for fk in PaperAccount.__table__.foreign_keys}
    assert "paper_runs.id" in fks


def test_paper_funds_unique_constraint():
    names = {c.name for c in PaperFunds.__table__.constraints}
    assert "uq_paper_funds_account_id" in names
    cols = set(PaperFunds.__table__.columns.keys())
    for name in ("account_id", "available_cash", "reserved_cash", "currency"):
        assert name in cols, f"missing paper_funds column {name}"


def test_migration_revision_chain_is_correct():
    migration = Path(__file__).resolve().parents[2] / "migrations" / "versions" / "20260820_paper_trading.py"
    text = migration.read_text(encoding="utf-8")
    assert 'revision = "20260820_paper_trading"' in text
    assert 'down_revision = "20260820_reconciliation_engine"' in text
    assert "paper_runs" in text
    assert "paper_accounts" in text
    assert "paper_funds" in text
