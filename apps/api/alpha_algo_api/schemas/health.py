from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service: str
    status: str
    live_trading: str


class ReadinessResponse(HealthResponse):
    checks: dict[str, str]


class EchoResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
