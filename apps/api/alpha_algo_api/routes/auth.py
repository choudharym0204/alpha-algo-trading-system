from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from alpha_algo_api.auth import (
    CurrentUser,
    Permissions,
    issue_access_token,
    issue_refresh_token,
    require_permission,
)
from alpha_algo_api.config import get_settings
from alpha_algo_api.db import get_db
from alpha_algo_api.errors import ApiError
from alpha_algo_api.rbac import resolve_user_permissions
from alpha_algo_api.schemas.auth import (
    CurrentUserResponse,
    LoginRequest,
    RefreshRequest,
    TokenResponse,
)
from alpha_algo_api.security.password import verify_password
from alpha_algo_api.security.tokens import TokenError, decode_token
from alpha_algo_shared.db import User

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _find_user_by_email(session: Session, email: str) -> User | None:
    return session.execute(select(User).where(User.email == email)).scalar_one_or_none()


@router.get("/me", response_model=CurrentUserResponse)
def me(
    user: Annotated[CurrentUser, Depends(require_permission(Permissions.SYSTEM_READ))],
) -> CurrentUserResponse:
    return CurrentUserResponse(
        subject=user.subject,
        permissions=sorted(user.permissions),
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, session: Annotated[Session, Depends(get_db)]) -> TokenResponse:
    user = _find_user_by_email(session, payload.email)
    if user is None or not verify_password(payload.password, user.password_hash):
        raise ApiError(
            code="AUTH_INVALID_CREDENTIALS",
            message="Invalid email or password.",
            status_code=401,
        )
    if not user.is_active:
        raise ApiError(
            code="AUTH_DISABLED",
            message="Account is disabled.",
            status_code=403,
        )

    permissions = resolve_user_permissions(session, user.id)
    settings = get_settings()
    return TokenResponse(
        access_token=issue_access_token(str(user.id), permissions),
        refresh_token=issue_refresh_token(str(user.id), permissions),
        token_type="bearer",
        expires_in=settings.access_token_ttl_minutes * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest) -> TokenResponse:
    settings = get_settings()
    try:
        token_payload = decode_token(
            payload.refresh_token,
            secret=settings.secret_key,
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            expected_type="refresh",
        )
    except TokenError as exc:
        raise ApiError(
            code="AUTH_INVALID",
            message="Invalid or expired refresh token.",
            status_code=401,
        ) from exc

    return TokenResponse(
        access_token=issue_access_token(token_payload.subject, token_payload.permissions),
        refresh_token=issue_refresh_token(token_payload.subject, token_payload.permissions),
        token_type="bearer",
        expires_in=settings.access_token_ttl_minutes * 60,
    )
