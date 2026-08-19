"""Database-backed RBAC permission resolution.

Resolves the union of permissions granted to a user through their roles using
the existing identity schema (``users``, ``roles``, ``permissions``,
``user_roles``, ``role_permissions``). No new migration is required.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from alpha_algo_shared.db import Permission, Role, User, role_permissions, user_roles


def resolve_user_permissions(session: Session, user_id: UUID) -> frozenset[str]:
    """Return the set of permission names granted to an active user via roles."""
    statement = (
        select(Permission.name)
        .join(role_permissions, role_permissions.c.permission_id == Permission.id)
        .join(Role, Role.id == role_permissions.c.role_id)
        .join(user_roles, user_roles.c.role_id == Role.id)
        .join(User, User.id == user_roles.c.user_id)
        .where(User.id == user_id)
        .where(User.is_active.is_(True))
        .distinct()
    )
    names = session.execute(statement).scalars().all()
    return frozenset(names)
