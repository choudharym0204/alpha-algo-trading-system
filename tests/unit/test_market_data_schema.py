from __future__ import annotations

from pathlib import Path

from sqlalchemy import UniqueConstraint

from alpha_algo_shared.db import Base
from migrations.runtime import target_metadata


def test_market_data_schema_tables_are_registered() -> None:
    expected = {"ticks", "candles", "market_depth", "indicator_values"}

    assert expected.issubset(set(Base.metadata.tables))
    assert target_metadata is Base.metadata


def test_market_data_schema_constraints_are_timescale_compatible() -> None:
    ticks = Base.metadata.tables["ticks"]
    candles = Base.metadata.tables["candles"]
    market_depth = Base.metadata.tables["market_depth"]
    indicator_values = Base.metadata.tables["indicator_values"]

    assert tuple(ticks.primary_key.columns.keys()) == ("id", "timestamp")
    assert tuple(candles.primary_key.columns.keys()) == ("id", "candle_start")
    assert tuple(market_depth.primary_key.columns.keys()) == ("id", "timestamp")
    assert tuple(indicator_values.primary_key.columns.keys()) == ("id", "calculated_at")

    unique_names = {
        constraint.name
        for table in (ticks, candles, market_depth, indicator_values)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert "uq_ticks_source_broker_sequence_timestamp" in unique_names
    assert "uq_candles_instrument_timeframe_start" in unique_names
    assert "uq_market_depth_source_broker_sequence_timestamp" in unique_names
    assert "uq_indicator_values_scope_name_timeframe_calculated_at" in unique_names


def test_market_data_migration_configures_timescaledb_hypertables() -> None:
    migration = Path("migrations/versions/20260812_timescale_market_data.py").read_text()

    assert "CREATE EXTENSION IF NOT EXISTS timescaledb" in migration
    assert "create_hypertable('ticks', 'timestamp'" in migration
    assert "create_hypertable('candles', 'candle_start'" in migration
    assert "create_hypertable('market_depth', 'timestamp'" in migration
    assert "create_hypertable('indicator_values', 'calculated_at'" in migration

