# Phase 10 — Broker Adapters — Session Report

**Date:** 2026-08-20
**Scope:** `services/broker_adapters/` (framework + Zerodha/Upstox/Angel One) + `tests/unit/test_broker_*.py` + `tests/unit/broker_test_support.py`
**Status:** COMPLETE — TESTED (not PRODUCTION)
**Full suite:** **1194 tests passing** (1117 baseline + 77 Phase 10)

---

## 1. What Phase 10 is

The broker-adapter layer is the **translation and isolation boundary** behind the
Phase-9 Execution Engine. The core system thinks in `OrderRequest` /
`OrderResponse` / `BrokerOrderEvent` / `PositionSnapshot` / `FundsSnapshot` /
`BrokerCapabilities` / `BrokerError`; the adapter thinks in Zerodha- / Upstox- /
Angel-One-specific terms. Provider-specific concepts never leak upward into
Strategy / Signal / Risk / OMS / Execution Core.

**Explicit scope boundary:** no Portfolio, no P&L, no Reconciliation, no
unrestricted LIVE. Phase 11+ owns those.

---

## 2. Architecture

```
Execution Engine (Phase 9)
        ↓
ExecutionAdapter (thin boundary)
        ↓
BrokerAdapter (Phase 10 universal contract)
        ├── Zerodha   (Kite Connect v3)
        ├── Upstox    (API v2)
        └── Angel One (SmartAPI)
        ↓
External Broker API / WebSocket
```

**Universal framework** — `services/broker_adapters/alpha_algo_broker_integration/`:

| Module | Responsibility |
|---|---|
| `contracts.py` | `BrokerAdapter` Protocol, `BrokerCapabilities`, `BrokerConnectionConfig`, `BrokerCredentialsRef`, order/response/snapshot dataclasses, `ConnectionState` |
| `errors.py` | `BrokerErrorClass` (12 classes) + `BrokerError` + retryability classification |
| `connection.py` | `ConnectionStateMachine` + `ReconnectPolicy` (bounded, jittered backoff) |
| `ratelimit.py` | per-scope `TokenBucket` + `RateLimiter` |
| `mapping.py` | `BrokerInstrument` + `InstrumentMapping` (resolve/validate), `validate_quantity`, `require_supported` |
| `transport.py` | `BrokerHttpTransport` Protocol + `HttpxTransport` + `FakeTransport` |
| `events.py` | `NormalizedBrokerEvent` + `EventDeduplicator` (dedup + conflict) |
| `base.py` | `BaseBrokerAdapter` (guards, connection, rate-limit, `_do_*` hooks) |

**Concrete adapters** — `zerodha/`, `upstox/`, `angel_one/`:
- `mapping.py` — status/error/order-type/product mapping tables + capabilities.
- `adapter.py` — concrete adapter (auth, payload builders, response/event parsers, `_do_*` transport calls).

---

## 3. Provider documentation basis (section 51)

| Broker | Documentation | Key facts recorded |
|---|---|---|
| Zerodha | Kite Connect v3 — https://kite.trade/docs/connect/v3/ | OAuth token auth (`api_key` + `access_token`); static IP required for order placement since **2025-04-01** |
| Upstox | Developer API v2 — https://upstox.com/developer/api-documentation/ | Bearer-token auth; V3 WebSocket (V2 discontinued **2025-08-22**); sandbox endpoints; `instrument_token` (not tradingsymbol) |
| Angel One | SmartAPI — https://smartapi.angelone.in/docs/ | `loginByPassword` (clientcode+password+TOTP) → JWT; static IP required for order execution since **2026-04-01**; WebSocket/postbacks |

Provider-specific error/status codes are mapped by HTTP status + documented error
codes; exact error-code lists should be re-verified against current docs at
deployment time (noted in `mapping.py`).

---

## 4. Universal contract coverage

`BrokerAdapter` Protocol methods: `authenticate`, `validate_session`, `logout`,
`connect`, `disconnect`, `health`, `reconnect`, `connection_state`,
`submit_order`, `modify_order`, `cancel_order`, `get_order`, `get_orders`,
`get_trades`, `get_positions`, `get_holdings`, `get_funds`.

Unsupported operations raise `BrokerError(UNSUPPORTED)` — never a silent fake.

---

## 5. Safety guarantees (sections 19, 35, 36)

- **LIVE blocked** — `LIVE` trading mode → `UNSUPPORTED` even with valid credentials.
- **GLOBAL_TRADING_HALT** — fail-closed (default active) blocks all submission.
- **No blind retry** — reconnect is a connection concern, decoupled from order
  submission; only `TRANSIENT_FAILURE`-class errors are retryable (and that retry
  policy lives in the Phase-9 engine, not the adapter).
- **No secret leakage** — credentials are opaque `secret_ref` strings; the resolver
  never prints them; source-scanned by tests; fake placeholders only in tests.

---

## 6. Capability isolation

Each adapter exposes `BrokerCapabilities` (supported exchanges/order-types/products/
modes/streams/account ops + broker-specific constraints). Unsupported order/product
types are rejected (`UNSUPPORTED`), never silently downgraded (e.g. Upstox has no
NRML; STOP never becomes MARKET).

---

## 7. Tests (77 new)

| File | Focus |
|---|---|
| `test_broker_contract.py` (28) | universal contract applied to all 3 adapters |
| `test_broker_mapping.py` (11) | status/order-type/product/error mapping |
| `test_broker_parsing.py` (11) | per-broker cancel/orders/positions/funds/events |
| `test_broker_errors.py` (12) | error normalization + failure injection |
| `test_broker_events.py` (6) | event dedup + conflict |
| `test_broker_concurrency.py` (5) | rate limit + duplicate-event safety |
| `test_broker_reconnect.py` (5) | bounded reconnect + backoff |
| `test_broker_security.py` (8) | LIVE gating + credential isolation + source scan |

---

## 8. Review

Four-axis adversarial review recorded in `review.md`: **0 BLOCKER, 0 MAJOR,
2 MINOR (fixed), 3 NOTE (documented)**.

---

## 9. LIVE status

- `LIVE_TRADING_ENABLED = false` and `GLOBAL_TRADING_HALT = true` remain unchanged.
- All adapters report `supports_live_trading=False`; no adapter is marked PRODUCTION
  (that requires real provider/sandbox + controlled-live validation).
- No real credentials anywhere; tests use `FakeTransport` + placeholder creds.

---

## 10. Register-file note

`TECHNOLOGY_STACK_REGISTER.md`, `PROVIDER_INTEGRATION_REGISTER.md`,
`CURRENT_ARCHITECTURE_REGISTER.md`, `TRADING_ENGINE_REGISTER.md`,
`PLATFORM_CAPABILITY_MATRIX.md`, `DEPENDENCY_REGISTER.md`,
`ARCHITECTURE_DEPENDENCY_GRAPH.md` do not exist as committed files; their content
is consolidated into `IMPLEMENTATION_STATUS.md` (§5.10 Broker Integration matrix
updated to TESTED, §0j added).

---

## 11. Known limitations

- No live broker connectivity/credentials in this environment → adapters are
  unit/mocked-tested against a `FakeTransport`; real sandbox verification is
  deferred.
- Instrument mapping is validated but the reverse (broker symbol → internal id)
  relies on a registered `InstrumentMapping`; unmapped symbols report a sentinel id
  for reconciliation (Phase 14).
- Per-broker error-code lists are best-effort and should be re-verified against
  current official docs at deployment time.
