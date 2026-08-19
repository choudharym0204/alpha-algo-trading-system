# Alpha Algo Trading System

This package is the Phase 0 architecture and governance baseline for the Alpha Algo Trading System.

The repository now also contains a monorepo skeleton. No trading runtime has been implemented yet. LIVE trading is disabled by design and must remain unavailable until the safety gates in `PROJECT_STATUS.md` and `MASTER_TASK_REGISTRY.md` are verified.

## Current Deliverables

- `docs/ARCHITECTURE.md` - system assessment, technology decision record, repository structure, domain architecture, Docker architecture, and roadmap.
- `docs/DATABASE.md` - proposed PostgreSQL/TimescaleDB architecture and ERD.
- `docs/API.md` - proposed API and WebSocket contract architecture.
- `docs/SECURITY.md` - security model and live-trading safety controls.
- `docs/TESTING.md` - unit, integration, trading-safety, and end-to-end test architecture.
- `docs/OPERATIONS.md` - observability, emergency stop, reconciliation, and operational runbook outline.
- `ARCHITECTURE_DECISIONS.md` - initial ADR log.
- `MASTER_TASK_REGISTRY.md` - implementation task registry.
- `PROJECT_STATUS.md` - current status, risks, and safety-gate state.
- Root `README.md`, `.gitignore`, and placeholder directories - Phase 0 skeleton only.
- Root `.env.example` - safe local-development placeholders only; no real secrets.
- Docker Compose foundation - infra-only services and observability profile.
- SQLAlchemy model foundation - declarative base and timestamp mixin.
- Alembic migration setup - revision scaffold and runtime helpers.
- Identity and RBAC schema - users, roles, permissions, and association tables.
- Instruments and broker account schema - exchanges, instruments, broker accounts, and broker sessions.
- Strategy, signal, order, trade, and position schema - trading-domain tables and constraints.
- Audit, risk, alert, and system event schema - safety, audit, notification, and append-only event tables.
- TimescaleDB market-data schema - ticks, candles, market depth, indicator values, and hypertable setup.
- FastAPI application foundation - app factory and non-trading system health/readiness endpoints.
- Request IDs, structured errors, and logging - request context middleware, error envelope, and request logging.
- Auth and RBAC service foundation - fail-closed bearer auth scaffolding and permission checks.
- WebSocket gateway foundation - authenticated non-trading gateway with initial `HEALTH_UPDATE`.
- Broker adapter interface - broker-independent async protocol and data contracts.
- Normalized market tick and candle contracts - broker-independent Pydantic contracts with validation.
- Stale-data and duplicate detection - deterministic market-data safety helpers.
- Deterministic indicator engine - SMA/EMA primitives with deterministic Decimal calculations.
- Strategy lifecycle interface - strategy hooks, context, validated signal emission, and no-order-placement boundary.
- Signal contracts and strategy versioning - broker-independent audit identity and advisory signal validation.
- Risk decision contracts - approval/rejection contracts with expiry safety and audit fields.
- Core risk rule engine - deterministic ordered rule evaluation with fail-safe rejection defaults.
- Global halt and live safety gates - default-disabled LIVE safety evaluator and global halt state.
- Order lifecycle state machine - broker-independent transitions with submitted-not-filled and reconciliation safety rules.
- Broker submission guard - fail-closed risk approval enforcement before submission can be requested.
- Broker order event handling - acknowledgements, partial fills, fills, rejects, cancellations, and unknown-state boundaries.
- Deterministic backtesting foundation - simulation clock, BACKTEST-mode isolation, explicit historical inputs, canonical sha256 manifests, audit records (P7-001).
- Paper trading foundation - PAPER-only simulator adapter, simulator-confirmed fills from injected reference prices, idempotent append-only paper book, PAPER-labeled positions, structural no-live-access tests (P8-001).
- Backtest simulation engine - deterministic fills, slippage, commissions, and performance metrics computed over explicit historical inputs with documented parameters; no reports, no persistence, BACKTEST-only (P7-002).
- Walk-forward testing harness - pure window scheduler + aggregation + overfitting assessment composing P7-001/P7-002: configurable train/validation/test windows, independent per-period results, exact-Decimal cross-period aggregation, fixed-threshold informational overfitting-risk flags (no auto-reject), caller-supplied runner contract, coverage metadata, in-memory only, hypothetical-results framing (P7-003).
- Backtest performance reports - pure deterministic report layer composing P7-001/P7-002: trade reconstruction (fill-sequence join), extended trade statistics, non-annualized Sortino/Calmar risk ratios, drawdown curve, daily/monthly/yearly return buckets, fixed REPORT_LIMITATIONS disclosure; hypothetical-results framing (P7-004).

## Phase 0 Validation State

- Repository inspected: yes.
- Existing code found: no.
- Existing database found: no.
- Existing tests found: no.
- Architecture baseline created: yes.
- Foundation skeleton started: yes.
- Trading implementation started: no.
- Live trading enabled: no.
