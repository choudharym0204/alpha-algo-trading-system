# Testing Architecture

This document is a proposal. No tests currently exist.

## Test Layers

Unit tests:

- Indicators.
- Strategy lifecycle.
- Signal generation.
- Risk rules.
- Position calculations.
- P&L calculations.
- Order validation.

Integration tests:

- PostgreSQL persistence.
- TimescaleDB hypertables.
- Redis transient state.
- Broker adapter contract tests.
- Market data pipeline.
- Execution pipeline.

Trading safety tests:

- Duplicate orders.
- Partial fills.
- Rejected orders.
- Broker timeout.
- WebSocket disconnect.
- Stale market data.
- Daily loss breach.
- Position limit breach.
- Unexpected position.
- Engine restart.
- Redis failure.
- Database failure.
- Risk engine failure.

End-to-end tests:

```text
Login
  -> Dashboard
  -> Strategy
  -> Signal
  -> Risk
  -> Order
  -> Fill
  -> Position
  -> P&L
```

## Verification Policy

A task is complete only when it is:

```text
IMPLEMENTED
TESTED
VERIFIED
DOCUMENTED
```

Live trading cannot be enabled from unit tests alone. It requires integration, safety, reconciliation, monitoring, and operational verification.

