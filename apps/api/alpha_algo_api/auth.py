"""Production authentication and RBAC enforcement.

Replaces the development-only ``DEV_TOKENS`` placeholder with real signed JWT
authentication. Access tokens carry a ``permissions`` claim that is enforced by
``require_permission``; the DB-backed resolution path lives in ``rbac.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from alpha_algo_api.config import get_settings
from alpha_algo_api.errors import ApiError
from alpha_algo_api.security.tokens import TokenError, create_token, decode_token

security = HTTPBearer(auto_error=False)


class Permissions:
    SYSTEM_READ = "system:read"
    TRADING_VIEW = "trading:view"
    PAPER_TRADE = "trading:paper"
    LIVE_TRADE = "trading:live"


@dataclass(frozen=True)
class CurrentUser:
    subject: str
    permissions: frozenset[str]

    def has_permission(self, permission: str) -> bool:
        return permission in self.permissions


def _token_secret() -> str:
    return get_settings().secret_key


def _token_issuer() -> str:
    return get_settings().jwt_issuer


def _token_audience() -> str:
    return get_settings().jwt_audience


def issue_access_token(
    subject: str,
    permissions: frozenset[str] | list[str],
    *,
    ttl_minutes: int | None = None,
) -> str:
    settings = get_settings()
    return create_token(
        subject=subject,
        permissions=permissions,
        token_type="access",
        ttl_seconds=(ttl_minutes or settings.access_token_ttl_minutes) * 60,
        secret=settings.secret_key,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
    )


def issue_refresh_token(
    subject: str,
    permissions: frozenset[str] | list[str],
    *,
    ttl_minutes: int | None = None,
) -> str:
    settings = get_settings()
    return create_token(
        subject=subject,
        permissions=permissions,
        token_type="refresh",
        ttl_seconds=(ttl_minutes or settings.refresh_token_ttl_minutes) * 60,
        secret=settings.secret_key,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
    )


def authenticate(credentials: HTTPAuthorizationCredentials | None) -> CurrentUser:
    if credentials is None:
        raise ApiError(
            code="AUTH_REQUIRED",
            message="Authentication required.",
            status_code=401,
        )
    if credentials.scheme.lower() != "bearer":
        raise ApiError(
            code="AUTH_INVALID",
            message="Unsupported authentication scheme.",
            status_code=401,
        )

    settings = get_settings()
    try:
        payload = decode_token(
            credentials.credentials,
            secret=settings.secret_key,
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            expected_type="access",
        )
    except TokenError as exc:
        raise ApiError(
            code="AUTH_INVALID",
            message="Invalid or expired authentication token.",
            status_code=401,
        ) from exc

    return CurrentUser(subject=payload.subject, permissions=payload.permissions)


def authenticate_token(token: str | None) -> CurrentUser:
    if token is None:
        raise ApiError(
            code="AUTH_REQUIRED",
            message="Authentication required.",
            status_code=401,
        )
    return authenticate(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token))


def require_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> CurrentUser:
    return authenticate(credentials)


def require_permission(permission: str):
    def dependency(
        request: Request,
        user: Annotated[CurrentUser, Depends(require_user)],
    ) -> CurrentUser:
        if not user.has_permission(permission):
            raise ApiError(
                code="FORBIDDEN",
                message="Required permission is missing.",
                status_code=403,
                details={
                    "permission": permission,
                    "request_id": getattr(request.state, "request_id", "unknown"),
                },
            )
        return user

    return dependency
