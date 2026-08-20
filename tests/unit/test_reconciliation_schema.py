"""Phase 14 — reconciliation schema tests."""

from __future__ import annotations

from pathlib import Path

from alpha_algo_shared.db.models.reconciliation import (
    ReconciliationDiscrepancy,
    ReconciliationRun,
)


def test_reconciliation_run_columns():
    cols = set(ReconciliationRun.__table__.columns.keys())
    for name in (
        "account_id", "broker", "trading_mode", "scope", "status", "started_at",
        "completed_at", "matched", "mismatched", "internal_only", "broker_only",
        "unknown", "unavailable", "skipped", "conflicts", "error",
    ):
        assert name in cols, f"missing reconciliation_runs column {name}"


def test_reconciliation_discrepancy_columns():
    cols = set(ReconciliationDiscrepancy.__table__.columns.keys())
    for name in (
        "discrepancy_key", "run_id", "account_id", "broker", "trading_mode",
        "entity_type", "entity_id", "kind", "severity", "internal_state",
        "broker_state", "resolution_status", "content_hash", "observed_at",
    ):
        assert name in cols, f"missing reconciliation_discrepancies column {name}"


def test_discrepancy_unique_constraint_and_indexes():
    names = {c.name for c in ReconciliationDiscrepancy.__table__.constraints}
    assert "uq_reconciliation_discrepancies_key" in names
    index_names = {ix.name for ix in ReconciliationDiscrepancy.__table__.indexes}
    assert "ix_reconciliation_discrepancies_run_id" in index_names
    assert "ix_reconciliation_discrepancies_account_id" in index_names


def test_migration_revision_chain_is_correct():
    migration = Path(__file__).resolve().parents[2] / "migrations" / "versions" / "20260820_reconciliation_engine.py"
    text = migration.read_text(encoding="utf-8")
    assert 'revision = "20260820_reconciliation_engine"' in text
    assert 'down_revision = "20260820_pnl_engine"' in text
    assert "reconciliation_runs" in text
    assert "reconciliation_discrepancies" in text
