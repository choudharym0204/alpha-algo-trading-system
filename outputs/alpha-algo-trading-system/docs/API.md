# API Architecture

This document is partially implemented. The FastAPI foundation, system health/readiness endpoints, request IDs, structured error envelope, request logging, auth/RBAC scaffolding, and WebSocket gateway foundation are implemented. Trading workflows and broker-facing runtime behavior are not implemented.

## REST Namespaces

```text
/api/v1/auth
/api/v1/users
/api/v1/brokers
/api/v1/instruments
/api/v1/market
/api/v1/strategies
/api/v1/signals
/api/v1/orders
/api/v1/positions
/api/v1/portfolio
/api/v1/risk
/api/v1/backtests
/api/v1/alerts
/api/v1/system
```

## API Rules

- Public API contracts must use Pydantic schemas.
- Internal database models must not be returned directly.
- All state-changing requests require authentication, authorization, request IDs, audit logging, and idempotency where applicable.
- Frontend requests can start, stop, configure, and inspect strategies only through backend APIs.
- Frontend code must never directly place broker orders.
- LIVE mode activation requires an explicit backend safety-gate workflow.

## WebSocket Event Types

```text
MARKET_TICK
ORDER_UPDATE
POSITION_UPDATE
PNL_UPDATE
STRATEGY_UPDATE
RISK_ALERT
SYSTEM_ALERT
HEALTH_UPDATE
```

## Consistent Error Shape

```json
{
  "error": {
    "code": "RISK_REJECTED",
    "message": "Order rejected by risk engine.",
    "request_id": "req_...",
    "details": {}
  }
}
```

## Trading Mode Contract

Allowed modes:

```text
BACKTEST
PAPER
LIVE
```

Mode constraints:

- No automatic PAPER to LIVE switching.
- Paper positions and live positions must never mix.
- LIVE must remain unavailable until all safety gates are verified.
