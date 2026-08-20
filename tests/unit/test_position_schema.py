"""Phase 11 — schema/migration integrity tests."""

from __future__ import annotations

from sqlalchemy import UniqueConstraint

from alpha_algo_shared.db import Base


def test_positions_has_last_execution_id_column():
    positions = Base.metadata.tables["positions"]
    assert "last_execution_id" in positions.c
    col = positions.c.last_execution_id
    assert col.nullable is True
    assert str(col.type).startswith("VARCHAR(64)") or col.type.length == 64


def test_positions_identity_unique_constraint_preserved():
    positions = Base.metadata.tables["positions"]
    uniques = {
        c.name for c in positions.constraints if isinstance(c, UniqueConstraint)
    }
    assert "uq_positions_strategy_run_id_instrument_id_trading_mode" in uniques


def test_position_events_identity_unique_for_idempotency():
    events = Base.metadata.tables["position_events"]
    assert events.c.source_event_id.unique is True
    assert events.c.position_id.foreign_keys  # FK back to positions


def test_position_migration_chain_points_to_execution_head():
    import importlib.util
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "versions"
        / "20260820_position_engine.py"
    )
    spec = importlib.util.spec_from_file_location("_p11_mig", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.revision == "20260820_position_engine"
    assert mod.down_revision == "20260819_execution"
