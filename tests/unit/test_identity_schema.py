from __future__ import annotations

from alpha_algo_shared.db import Base
from migrations.runtime import target_metadata


def test_identity_schema_tables_are_registered() -> None:
    expected = {"users", "roles", "permissions", "user_roles", "role_permissions"}

    assert expected.issubset(set(Base.metadata.tables))
    assert target_metadata is Base.metadata


def test_identity_schema_constraints_are_present() -> None:
    users = Base.metadata.tables["users"]
    roles = Base.metadata.tables["roles"]
    permissions = Base.metadata.tables["permissions"]
    user_roles = Base.metadata.tables["user_roles"]
    role_permissions = Base.metadata.tables["role_permissions"]

    assert users.c.email.unique is True
    assert roles.c.name.unique is True
    assert permissions.c.name.unique is True
    assert tuple(user_roles.primary_key.columns.keys()) == ("user_id", "role_id")
    assert tuple(role_permissions.primary_key.columns.keys()) == ("role_id", "permission_id")

