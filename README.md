# Alpha Algo Trading System

Production-grade algorithmic trading infrastructure, currently entering Phase 8 paper trading foundations.

This repository does not yet contain trading runtime code. LIVE trading is disabled and unavailable until all safety gates are implemented, tested, verified, documented, and operationally approved.

## Current Status

- Architecture and governance baseline: implemented.
- Monorepo skeleton: implemented.
- Safe environment template: verified.
- Docker Compose foundation: verified.
- CI skeleton: verified.
- SQLAlchemy model foundation: verified.
- Alembic migration setup: verified.
- Identity and RBAC schema: verified.
- Instruments and broker account schema: verified.
- Strategy, signal, order, trade, and position schema: verified.
- Audit, risk, alert, and system event schema: verified.
- TimescaleDB tick/candle schema: verified.
- FastAPI application foundation: verified.
- Request IDs, structured errors, and logging: verified.
- Auth and RBAC service foundation: verified.
- WebSocket gateway foundation: verified.
- Broker adapter interface: verified.
- Normalized market tick and candle contracts: verified.
- Stale-data and duplicate detection: verified.
- Deterministic indicator engine: verified.
- Strategy lifecycle interface: verified.
- Signal contracts and strategy versioning: verified.
- Risk decision contracts: verified.
- Core risk rule engine: verified.
- Global halt and live safety gate primitives: verified.
- Order lifecycle state machine: verified.
- Broker submission guard: verified.
- Broker event handling: verified.
- Backtesting foundation: verified.
- Paper trading foundation: verified (PAPER-only simulator adapter, simulator-confirmed fills from injected reference prices; operational paper trading — persistence, reconciliation, P&L — is not implemented).
- Paper market-data feed bridge: verified (deterministic PAPER-scoped conversion of caller-supplied MarketTick records into PaperReferencePrice snapshots for simulator-confirmed fills; no fetching, no live ingestion, no persistence).
- Walk-forward testing harness: verified (configurable train/validation/test windows over explicit history, independent per-period results, exact-Decimal cross-period aggregation, informational overfitting-risk flags; hypothetical-results framing; no strategy fitting, no persistence, no LIVE implication).
- Backtest performance reports: verified (pure deterministic report layer composing the engine: trade reconstruction, extended trade statistics, non-annualized risk ratios, drawdown curve, daily/monthly/yearly return buckets; hypothetical-results framing; no persistence, no LIVE implication).
- Application trading runtime: not implemented.
- Database migrations: Phase 1 foundation verified.
- Broker adapter implementations: not implemented.
- Strategy runtime: not implemented.
- Backtest simulation engine (fills, slippage, metrics): verified; backtest performance reports: verified; backtest run persistence: not implemented.
- Paper trading operational runtime: not implemented.
- LIVE trading: disabled.

## Primary Governance Files

- [Master implementation prompt](MASTER_IMPLEMENTATION_PROMPT.md)
- [Project status](outputs/alpha-algo-trading-system/PROJECT_STATUS.md)
- [Master task registry](outputs/alpha-algo-trading-system/MASTER_TASK_REGISTRY.md)
- [Architecture decisions](outputs/alpha-algo-trading-system/ARCHITECTURE_DECISIONS.md)
- [Architecture](outputs/alpha-algo-trading-system/docs/ARCHITECTURE.md)
- [Database architecture](outputs/alpha-algo-trading-system/docs/DATABASE.md)
- [API architecture](outputs/alpha-algo-trading-system/docs/API.md)
- [Security architecture](outputs/alpha-algo-trading-system/docs/SECURITY.md)
- [Testing architecture](outputs/alpha-algo-trading-system/docs/TESTING.md)
- [Operations architecture](outputs/alpha-algo-trading-system/docs/OPERATIONS.md)

## Planned Repository Structure

```text
apps/
services/
packages/
backtesting/
migrations/
tests/
docs/
scripts/
infra/
docker/
```

## Next Task

The next implementation task is:

```text
Paper trading operational runtime (persistence, reconciliation, P&L) or frontend trading terminal — the next dependency after P8-002 - Paper market-data feed
```

All 17 LIVE safety gates remain TODO; LIVE trading stays disabled and unavailable.

Do not add real broker credentials or secrets to this repository.
