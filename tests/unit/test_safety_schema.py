from __future__ import annotations

from sqlalchemy import UniqueConstraint

from alpha_algo_shared.db import Base
from migrations.runtime import target_metadata


def test_safety_schema_tables_are_registered() -> None:
    expected = {
        "risk_rules",
        "risk_events",
        "order_events",
        "position_events",
        "portfolio_snapshots",
        "alerts",
        "notifications",
        "audit_logs",
        "system_events",
    }

    assert expected.issubset(set(Base.metadata.tables))
    assert target_metadata is Base.metadata


def test_safety_schema_constraints_are_present() -> None:
    risk_rules = Base.metadata.tables["risk_rules"]
    risk_events = Base.metadata.tables["risk_events"]
    order_events = Base.metadata.tables["order_events"]
    position_events = Base.metadata.tables["position_events"]
    portfolio_snapshots = Base.metadata.tables["portfolio_snapshots"]
    alerts = Base.metadata.tables["alerts"]
    notifications = Base.metadata.tables["notifications"]
    audit_logs = Base.metadata.tables["audit_logs"]
    system_events = Base.metadata.tables["system_events"]
    orders = Base.metadata.tables["orders"]

    assert risk_rules.c.code.unique is True
    assert risk_rules.c.name.unique is True
    assert risk_events.c.approval_id.unique is True
    assert order_events.c.source_event_id.unique is True
    assert position_events.c.source_event_id.unique is True
    assert alerts.c.deduplication_key.unique is True
    assert notifications.c.delivery_reference.unique is True
    assert audit_logs.c.event_hash.unique is True
    assert system_events.c.source_event_id.unique is True
    assert orders.c.risk_event_id.nullable is True

    snapshot_uniques = {
        constraint.name
        for constraint in portfolio_snapshots.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert "uq_portfolio_snapshots_account_mode_snapshot_at" in snapshot_uniques
    assert risk_events.c.decision.nullable is False
    assert audit_logs.c.event_timestamp.nullable is False
    assert alerts.c.status.server_default is not None

