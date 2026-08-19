from __future__ import annotations

from sqlalchemy import UniqueConstraint

from alpha_algo_shared.db import Base
from migrations.runtime import target_metadata


def test_reference_schema_tables_are_registered() -> None:
    expected = {"exchanges", "instruments", "broker_accounts", "broker_sessions"}

    assert expected.issubset(set(Base.metadata.tables))
    assert target_metadata is Base.metadata


def test_reference_schema_constraints_are_present() -> None:
    exchanges = Base.metadata.tables["exchanges"]
    instruments = Base.metadata.tables["instruments"]
    broker_accounts = Base.metadata.tables["broker_accounts"]
    broker_sessions = Base.metadata.tables["broker_sessions"]

    assert exchanges.c.code.unique is True
    assert exchanges.c.name.unique is True
    assert exchanges.c.mic_code.unique is True

    instrument_uniques = {
        constraint.name
        for constraint in instruments.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    broker_account_uniques = {
        constraint.name
        for constraint in broker_accounts.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert "uq_instruments_exchange_id_symbol" in instrument_uniques
    assert "uq_broker_accounts_broker_name_account_identifier" in broker_account_uniques
    assert broker_sessions.c.session_token_ref.nullable is True

