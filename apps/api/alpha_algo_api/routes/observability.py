"""Read-only observability endpoint (Phase 20 §28, §48).

Exposes a single operational snapshot — metrics, health (including trading
safety), alerts, and recent traces — for dashboards. It is strictly a
visibility surface: gated by ``system:read`` and read-only. It can never flip
trading mode, enable LIVE, or modify financial state (Phase 20 §2, §28).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from alpha_algo_api.auth import CurrentUser, Permissions, require_permission
from alpha_algo_api.config import get_settings
from alpha_algo_observability import (
    get_alert_manager,
    get_health_registry,
    get_metrics,
    get_trace_context,
)

router = APIRouter(prefix="/api/v1/system", tags=["observability"])


@router.get("/observability")
def observability(
    _user: CurrentUser = Depends(require_permission(Permissions.SYSTEM_READ)),
) -> dict[str, Any]:
    settings = get_settings()
    health = get_health_registry().snapshot()
    return {
        "service": settings.app_name,
        "environment": settings.app_env,
        "version": "0.1.0",
        "trading_safety": {
            "live_trading_enabled": settings.live_trading_enabled,
            "global_trading_halt": settings.global_trading_halt,
            "default_trading_mode": settings.default_trading_mode,
        },
        "health": health.to_dict(),
        "metrics": get_metrics().snapshot(),
        "alerts": get_alert_manager().list(),
        "traces": get_trace_context().store.spans(),
    }
