from __future__ import annotations

from sqlalchemy import UniqueConstraint

from alpha_algo_shared.db import Base
from migrations.runtime import target_metadata


def test_trading_schema_tables_are_registered() -> None:
    expected = {
        "strategies",
        "strategy_versions",
        "strategy_configs",
        "strategy_runs",
        "signals",
        "orders",
        "trades",
        "positions",
    }

    assert expected.issubset(set(Base.metadata.tables))
    assert target_metadata is Base.metadata


def test_trading_schema_constraints_are_present() -> None:
    strategies = Base.metadata.tables["strategies"]
    strategy_versions = Base.metadata.tables["strategy_versions"]
    strategy_configs = Base.metadata.tables["strategy_configs"]
    strategy_runs = Base.metadata.tables["strategy_runs"]
    orders = Base.metadata.tables["orders"]
    trades = Base.metadata.tables["trades"]
    positions = Base.metadata.tables["positions"]

    assert strategies.c.code.unique is True
    assert strategies.c.name.unique is True
    assert strategy_versions.c.definition_hash.unique is True
    assert strategy_configs.c.config_hash.unique is True
    assert orders.c.client_order_id.unique is True
    assert orders.c.broker_order_id.unique is True
    assert trades.c.broker_trade_id.unique is True
    assert strategy_runs.c.status.server_default is not None

    version_uniques = {
        constraint.name
        for constraint in strategy_versions.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    config_uniques = {
        constraint.name
        for constraint in strategy_configs.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    run_uniques = {
        constraint.name
        for constraint in strategy_runs.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    position_uniques = {
        constraint.name
        for constraint in positions.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert "uq_strategy_versions_strategy_id_version_label" in version_uniques
    assert "uq_strategy_configs_strategy_version_id_config_name" in config_uniques
    assert "uq_strategy_runs_strategy_version_id_run_label" in run_uniques
    assert "uq_positions_strategy_run_id_instrument_id_trading_mode" in position_uniques
    assert orders.c.strategy_run_id.nullable is True
    assert strategies.c.is_active.nullable is False

