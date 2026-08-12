# Operations Architecture

This document is a proposal. No operational runtime currently exists.

## Observability

Required telemetry:

- Market-data latency.
- WebSocket latency.
- Order latency.
- Order rejection rate.
- Strategy execution latency.
- API latency.
- Database latency.
- Redis health.
- Broker health.
- Worker health.
- Risk rejection rate.

Planned tools:

- Structured JSON logging.
- Prometheus metrics.
- Grafana dashboards.
- Sentry-compatible exception reporting.
- Health endpoints for every critical service.

## Emergency Stop

Emergency stop flow:

```text
EMERGENCY STOP
  -> STOP NEW ORDERS
  -> DISABLE STRATEGIES
  -> CANCEL PENDING ORDERS
  -> OPTIONAL SQUARE-OFF
```

Emergency stop must create audit events and alerts.

## Circuit Breakers

Initial breakers:

- Daily loss exceeded.
- Broker disconnected.
- Market data stale.
- Unexpected position.
- Excessive rejected orders.
- Trading engine failure.
- Risk engine failure.
- Execution engine failure.

If the risk engine is unavailable, live trading must stop.

## Reconciliation

Periodic reconciliation compares:

```text
Internal positions
  vs
Broker positions
```

Mismatch classes:

- Quantity mismatch.
- Average price mismatch.
- Unknown position.
- Missing position.
- Unexpected position.
- Broker-side change.

Unexpected live positions should trigger alerts and configurable trading halts.

