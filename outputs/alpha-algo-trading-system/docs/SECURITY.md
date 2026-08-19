# Security Architecture

This document is partially implemented. Identity/RBAC database schema and fail-closed auth/RBAC API scaffolding exist. Production credential handling, session management, broker secret storage, live safety workflows, and full audit runtime behavior are not implemented.

## Non-Negotiable Security Boundaries

- Broker secrets must never be stored in frontend code.
- Broker secrets must never be sent to browsers.
- Frontend code must never directly place broker orders.
- Strategies must never bypass the risk engine.
- Execution engine must reject live orders without valid risk approval.
- If the risk engine is unavailable, live trading must stop.
- If market data is stale, new live orders must be blocked.

## Identity and Access

Planned controls:

- Secure password handling or external identity provider integration.
- Session management with expiration and revocation.
- RBAC with least-privilege permissions.
- Separate permissions for viewing, configuring, paper trading, and live trading.
- Explicit elevated confirmation for emergency stop and live enablement.

## Secrets

Broker credentials:

- Store encrypted at rest.
- Decrypt only inside backend broker-management or broker-adapter services.
- Never log credentials.
- Rotate tokens where broker APIs support it.
- Use environment-based secrets for infrastructure configuration.

## Audit Trail

Critical events must record:

```text
timestamp
user_id
strategy_id
strategy_version
instrument
broker
signal_id
risk_decision
order_id
event_type
status
reason
request_id
```

## Live Trading Safety Gate

LIVE mode remains disabled until these areas are implemented and verified:

- Market data stability.
- Broker connection stability.
- Strategy tests.
- Risk tests.
- Execution tests.
- Reconciliation.
- Paper trading verification.
- Emergency stop.
- Circuit breakers.
- Position and P&L calculations.
- Duplicate-order protection.
- Broker failure handling.
- Database persistence.
- Audit logging.
- Monitoring.
- Security checks.
