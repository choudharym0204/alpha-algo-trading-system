# Master Task Registry

Statuses: TODO, IN_PROGRESS, BLOCKED, IMPLEMENTED, VERIFIED, PRODUCTION_READY

## Phase 0 - Foundation

| Task ID | Description | Priority | Status | Files | Dependencies | Tests | Risk | Verification | Completion Date |
|---|---|---:|---|---|---|---|---|---|---|
| P0-001 | Inspect repository and environment | P0 | VERIFIED | README.md | None | N/A | Low | Workspace inspected; no existing repo found | 2026-08-12 |
| P0-002 | Create architecture baseline | P0 | IMPLEMENTED | docs/ARCHITECTURE.md | P0-001 | Documentation review | Medium | Pending user architecture validation | 2026-08-12 |
| P0-003 | Create database architecture proposal | P0 | IMPLEMENTED | docs/DATABASE.md | P0-002 | Documentation review | High | Pending user architecture validation | 2026-08-12 |
| P0-004 | Create API architecture proposal | P0 | IMPLEMENTED | docs/API.md | P0-002 | Documentation review | Medium | Pending user architecture validation | 2026-08-12 |
| P0-005 | Create security and live safety architecture | P0 | IMPLEMENTED | docs/SECURITY.md | P0-002 | Documentation review | Critical | Pending user architecture validation | 2026-08-12 |
| P0-006 | Create testing architecture | P0 | IMPLEMENTED | docs/TESTING.md | P0-002 | Documentation review | High | Pending user architecture validation | 2026-08-12 |
| P0-007 | Create operations architecture | P0 | IMPLEMENTED | docs/OPERATIONS.md | P0-002 | Documentation review | High | Pending user architecture validation | 2026-08-12 |
| P0-008 | Initialize repository skeleton | P0 | TODO | repo root | P0-002 through P0-007 | Lint, typecheck, smoke tests | Medium | Not started | |
| P0-009 | Add Docker Compose foundation | P0 | TODO | docker-compose*.yml | P0-008 | Compose config validation | Medium | Not started | |
| P0-010 | Add CI skeleton | P1 | TODO | .github/workflows | P0-008 | CI dry run where possible | Medium | Not started | |
| P0-011 | Add `.env.example` with safe placeholders | P0 | TODO | .env.example | P0-008 | Secret scan | High | Not started | |

## Phase 1 - Database

| Task ID | Description | Priority | Status | Files | Dependencies | Tests | Risk | Verification | Completion Date |
|---|---|---:|---|---|---|---|---|---|---|
| P1-001 | Add SQLAlchemy model foundation | P0 | TODO | apps/api, packages/shared | P0-008 | Unit tests | High | Not started | |
| P1-002 | Add Alembic migration setup | P0 | TODO | migrations | P1-001 | Migration up/down tests | High | Not started | |
| P1-003 | Add identity and RBAC schema | P0 | TODO | migrations | P1-002 | DB constraint tests | High | Not started | |
| P1-004 | Add instruments and broker account schema | P0 | TODO | migrations | P1-002 | DB constraint tests | High | Not started | |
| P1-005 | Add strategy, signal, order, trade, and position schema | P0 | TODO | migrations | P1-002 | Trading persistence tests | Critical | Not started | |
| P1-006 | Add audit, risk, alert, and system event schema | P0 | TODO | migrations | P1-002 | Audit immutability tests | Critical | Not started | |
| P1-007 | Add TimescaleDB tick/candle schema | P1 | TODO | migrations | P1-002 | Hypertable tests | High | Not started | |

## Phase 2 - Backend

| Task ID | Description | Priority | Status | Files | Dependencies | Tests | Risk | Verification | Completion Date |
|---|---|---:|---|---|---|---|---|---|---|
| P2-001 | Add FastAPI application foundation | P0 | TODO | apps/api | P0-008 | API smoke tests | Medium | Not started | |
| P2-002 | Add request IDs, structured errors, and logging | P0 | TODO | apps/api | P2-001 | Unit tests | Medium | Not started | |
| P2-003 | Add auth and RBAC service foundation | P0 | TODO | apps/api | P1-003, P2-001 | Auth tests | High | Not started | |
| P2-004 | Add WebSocket gateway foundation | P1 | TODO | apps/api | P2-001 | WS tests | Medium | Not started | |

## Phase 3 - Market Data

| Task ID | Description | Priority | Status | Files | Dependencies | Tests | Risk | Verification | Completion Date |
|---|---|---:|---|---|---|---|---|---|---|
| P3-001 | Add broker adapter interface | P0 | TODO | packages/broker_adapters | P0-008 | Contract tests | Critical | Not started | |
| P3-002 | Add normalized market tick and candle contracts | P0 | TODO | packages/contracts | P3-001 | Schema tests | High | Not started | |
| P3-003 | Add stale-data and duplicate detection | P0 | TODO | services/market_data | P3-002 | Trading safety tests | Critical | Not started | |

## Phase 4 - Indicators and Strategies

| Task ID | Description | Priority | Status | Files | Dependencies | Tests | Risk | Verification | Completion Date |
|---|---|---:|---|---|---|---|---|---|---|
| P4-001 | Add deterministic indicator engine | P1 | TODO | packages/indicators | P0-008 | Unit tests | Medium | Not started | |
| P4-002 | Add strategy lifecycle interface | P0 | TODO | packages/strategies | P3-002 | Unit tests | Critical | Not started | |
| P4-003 | Add signal contracts and strategy versioning | P0 | TODO | packages/contracts | P4-002 | Contract tests | Critical | Not started | |

## Phase 5 - Risk Engine

| Task ID | Description | Priority | Status | Files | Dependencies | Tests | Risk | Verification | Completion Date |
|---|---|---:|---|---|---|---|---|---|---|
| P5-001 | Add risk decision contracts | P0 | TODO | packages/contracts | P4-003 | Contract tests | Critical | Not started | |
| P5-002 | Add core risk rule engine | P0 | TODO | services/risk_engine | P5-001 | Risk tests | Critical | Not started | |
| P5-003 | Add global halt and live safety gates | P0 | TODO | services/risk_engine | P5-002 | Trading safety tests | Critical | Not started | |

## Phase 6 - Execution

| Task ID | Description | Priority | Status | Files | Dependencies | Tests | Risk | Verification | Completion Date |
|---|---|---:|---|---|---|---|---|---|---|
| P6-001 | Add order lifecycle state machine | P0 | TODO | services/execution_engine | P5-001 | Unit tests | Critical | Not started | |
| P6-002 | Enforce valid risk approval before broker submission | P0 | TODO | services/execution_engine | P5-002, P6-001 | Trading safety tests | Critical | Not started | |
| P6-003 | Add partial fill, reject, cancel, and unknown-state handling | P0 | TODO | services/execution_engine | P6-001 | Trading safety tests | Critical | Not started | |

## Later Phases

Backtesting, paper trading, frontend terminal, live trading, and production hardening remain TODO until earlier safety-critical foundations are implemented and verified.

