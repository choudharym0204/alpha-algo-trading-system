from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class DatabaseUnavailableError(Exception):
    """Raised when the database cannot be reached at startup or on a health check.

    This is deliberately a plain ``Exception`` (not an ``ApiError``) so that
    connection details are never echoed to clients; the handler below maps it to
    a generic 503 envelope.
    """


def build_error_response(
    *,
    code: str,
    message: str,
    request_id: str,
    status_code: int,
    details: dict[str, Any] | list[Any] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": request_id,
                "details": details or {},
            },
        },
        headers={"x-request-id": request_id},
    )


# Keys safe to echo back to the client from a pydantic validation error.
# "input" and "ctx" can carry raw request values (passwords, tokens, etc.).
_SAFE_VALIDATION_KEYS = {"type", "loc", "msg"}


def _sanitize_validation_errors(errors: list[Any]) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    for error in errors:
        if isinstance(error, dict):
            sanitized.append(
                {key: value for key, value in error.items() if key in _SAFE_VALIDATION_KEYS}
            )
        else:
            sanitized.append({"msg": str(error)})
    return sanitized


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    return build_error_response(
        code="HTTP_ERROR",
        message=str(exc.detail),
        request_id=request_id,
        status_code=exc.status_code,
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    return build_error_response(
        code="VALIDATION_ERROR",
        message="Request validation failed.",
        request_id=request_id,
        status_code=422,
        details={"errors": _sanitize_validation_errors(exc.errors())},
    )


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    return build_error_response(
        code=exc.code,
        message=exc.message,
        request_id=request_id,
        status_code=exc.status_code,
        details=exc.details,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    return build_error_response(
        code="INTERNAL_ERROR",
        message="Internal server error.",
        request_id=request_id,
        status_code=500,
    )


async def database_unavailable_handler(request: Request, exc: DatabaseUnavailableError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    return build_error_response(
        code="DATABASE_UNAVAILABLE",
        message="Database is unavailable.",
        request_id=request_id,
        status_code=503,
    )

