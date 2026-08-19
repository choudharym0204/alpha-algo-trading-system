from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

from alpha_algo_api.rbac import resolve_user_permissions


def test_resolve_user_permissions_returns_union() -> None:
    session = MagicMock()
    session.execute.return_value.scalars.return_value.all.return_value = [
        "system:read",
        "trading:view",
    ]

    result = resolve_user_permissions(session, uuid4())

    assert result == frozenset({"system:read", "trading:view"})
    session.execute.assert_called_once()


def test_resolve_user_permissions_empty() -> None:
    session = MagicMock()
    session.execute.return_value.scalars.return_value.all.return_value = []

    result = resolve_user_permissions(session, uuid4())

    assert result == frozenset()
    session.execute.assert_called_once()
