# P17-session-report.md — Phase 17: Web Platform

**Project:** Alpha Algo Trading System
**Date:** 2026-08-20
**Status:** COMPLETE — TESTED (never PRODUCTION / LIVE_READY)
**Backend baseline:** 1611 tests passing (Phases 1–16), 1 pre-existing warning (FastAPI `httpx` deprecation)
**Web result:** 29 tests passing (7 files), production build green (19 routes), backend regression unchanged at **1611**

---

## 1. Objective

Build the first production-grade **Web Trading Terminal** (`apps/web/`) on top of the verified backend contracts — a presentation/control layer that consumes the backend only through authenticated REST + WebSocket. The browser never accesses PostgreSQL, Redis, broker APIs, broker credentials, execution adapters, or internal service databases.

## 2. Backend contract discovery (honest scope)

Before building, the actual API surface was inspected (`apps/api/alpha_algo_api/`):

| Backend contract | Method | Path | Auth | Wired in web |
|---|---|---|---|---|
| Login | `POST` | `/api/v1/auth/login` | — | ✅ |
| Refresh | `POST` | `/api/v1/auth/refresh` | — | ✅ |
| Current user | `GET` | `/api/v1/auth/me` | `system:read` | ✅ |
| Health | `GET` | `/api/v1/system/health` | — | ✅ |
| Readiness | `GET` | `/api/v1/system/ready` | — | ✅ |
| Request-id | `GET` | `/api/v1/system/request-id` | — | (not used by UI) |
| WebSocket health | `WS` | `/api/v1/ws?token=…` | `system:read` | ✅ |

**There are no trading-data endpoints** (orders, positions, portfolio, P&L, strategies, risk, brokers, reconciliation, market data, watchlist). Per §7/§10/§49, those screens render an explicit **Unavailable** state — never fabricated zeros or mock data. No fake E2E "paper order → fill" flow was built, because the backend cross-engine REST orchestration boundary does not exist yet.

## 3. What was built (`apps/web/`)

- **Auth** — real login/refresh/me/logout/session-restoration/expiry/401/403 against the backend contract. Tokens held **in memory only** (backend returns JSON tokens, sets no httpOnly cookie → no safer storage mechanism).
- **RBAC** — `system:read` gates the shell, `trading:view` gates trading areas; server 401/403 is always the final authority and is handled gracefully. Permission names mirror `auth.py` (`system:read`, `trading:view`, `trading:paper`, `trading:live`).
- **Protected routing** — client-side route guard (`RequireAuth`) redirects unauthenticated → `/login`, blocks missing permission with explicit denial.
- **Application shell** — sidebar (permission-filtered nav), topbar, **PAPER/LIVE mode badge** (derived fail-closed from `health.live_trading`), **WebSocket connection indicator**, session controls, and a toast notification area.
- **Dashboard** — real system health/readiness (`service`, `api`, `database`, `broker` checks), trading-mode, LIVE-safety panel (`live_trading`, `LIVE_TRADING_ENABLED=false`, `GLOBAL_TRADING_HALT=true`), real-time `HEALTH_UPDATE` panel, and trading metrics shown as **Unavailable** (not zero).
- **Design system** — `Button`, `Input`, `Select`, `Modal`, `Table`, `Badge`, `Tabs`, `Toast`, `Tooltip`, `Skeleton`, `EmptyState`, `ErrorState`, `StatusIndicator` (dot **+** text, non-color-only).
- **REST client** — typed fetch wrapper that parses the backend structured error envelope and throws a normalized `ApiError`; never logs tokens.
- **WebSocket client** — authenticated `/api/v1/ws` with bounded-backoff reconnect, typed event validation (`normalizeWsEvent` drops malformed/unknown messages), connection status.
- **State** — server state (health/readiness/WS) separated from UI state; polled with staleness tracking.

## 4. Routes

| Route | Content | Backend data |
|---|---|---|
| `/login` | login form | auth |
| `/dashboard` | health/readiness/mode/safety/WS | system + WS |
| `/settings` | session + permissions + env | auth (`/me`) |
| `/markets` … `/alerts` | honest Unavailable states | none (not yet exposed) |

## 5. LIVE / PAPER safety

- `health.live_trading === "disabled"` → PAPER; `"enabled"` → LIVE; anything else → `UNKNOWN` (fail-closed, never LIVE).
- No UI toggle, no LIVE path, no frontend bypass. The badge is read-only.
- `TradingModeBadge` is tested to never render LIVE for a disabled/unknown backend.
- Broker credentials, API secrets, and tokens never reach the browser (in-memory token store, no `process.env` ad hoc reads, centralized `env.ts`).

## 6. Testing (29 tests, 7 files)

- `errors.test.ts` — backend envelope parse + safe fallback on non-envelope bodies.
- `permissions.test.ts` — RBAC gating (present/absent/null).
- `session-store.test.ts` — in-memory token lifecycle + 5s expiry skew.
- `trading-mode.test.ts` — fail-closed PAPER/LIVE/UNKNOWN derivation.
- `ws-client.test.ts` — typed event validation (valid/unknown/malformed/non-JSON).
- `trading-mode-badge.test.tsx` — LIVE never shown when disabled.
- `data-unavailable.test.tsx` — honest boundary, no fabricated zeros.

## 7. Verification

- `npm test` → **29 passed** (7 files).
- `npm run build` → **production build green**, 19 routes prerendered, strict TypeScript passed.
- Backend regression re-run → **1611 passed** (unchanged, 1 pre-existing warning).

## 8. Known limitations (honest)

- **Live backend E2E deferred** — no Docker/PostgreSQL in this environment, so the API cannot serve `/auth/login`/`/auth/me`. Contract shapes are verified by mirroring the backend Pydantic schemas + unit tests; full live E2E is VERIFIED/PRODUCTION-time work.
- **Trading data not wired** — the backend exposes no trading-data endpoints yet; all such screens are honest Unavailable states. No cross-engine REST orchestration boundary exists to drive a paper-order E2E.
- **Session is in-memory** — full reload requires re-authentication (documented, not a bug; no httpOnly-cookie mechanism exists in the backend).
- **TradingView Lightweight Charts / shadcn-ui not added** — no chart data endpoint exists, and a hand-rolled design system was chosen as the smallest maintainable structure (spec §2). Charts become real only when a backend OHLC endpoint lands.

## 9. Status

Phase 17 capabilities are **TESTED**, not `PRODUCTION` — `PRODUCTION` requires live-DB/provider E2E verification (Phase 24+). LIVE remains **fail-closed**.
