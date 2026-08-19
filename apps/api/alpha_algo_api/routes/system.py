from __future__ import annotations

from fastapi import APIRouter, Request

from alpha_algo_api.db import ping_database
from alpha_algo_api.schemas.health import EchoResponse, HealthResponse, ReadinessResponse

router = APIRouter(prefix="/api/v1/system", tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        service="alpha-algo-api",
        status="ok",
        live_trading="disabled",
    )


@router.get("/ready", response_model=ReadinessResponse)
def ready() -> ReadinessResponse:
    database = "ok" if ping_database() else "error"
    return ReadinessResponse(
        service="alpha-algo-api",
        status="ready",
        live_trading="disabled",
        checks={
            "api": "ok",
            "database": database,
            "broker": "disabled",
        },
    )


@router.get("/request-id", response_model=EchoResponse)
def request_id(request: Request) -> EchoResponse:
    return EchoResponse(request_id=request.state.request_id)
