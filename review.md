# Phase 17 — Web Platform — Adversarial Review

**Date:** 2026-08-20
**Backend baseline:** 1611 tests passing (Phases 1–16), 1 pre-existing warning (FastAPI deprecation, unrelated)
**Web added:** 29 tests (7 files); production build green (19 routes)
**Review method:** No external review subagents are available at the model/provider layer. This review was performed **inline** by the implementing agent and is recorded transparently; it does **not** claim independent reviewer separation. Every legitimate finding below was fixed and regression-tested.

---

## Review 1 — Web Architecture

**Scope:** structure, state management, API boundaries, component reuse, scalability, honesty of scope.

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 1.1 | OK | No pre-existing frontend existed (`apps/web/` was `.gitkeep`). A single new Next.js App Router app was created as the smallest maintainable structure — no second architecture, no unused framework. | Accepted (§2). |
| 1.2 | OK | Server state (health/readiness/WS) is separated from UI state; financial server state is not duplicated in local stores. Auth state lives in one `AuthProvider`. | Design (§27). |
| 1.3 | NOTE | **Next.js 14.2.5 was pinned initially and npm reported a security advisory.** | FIXED — upgraded to **14.2.35** (latest patched 14.x); reinstall clean, no advisory. |
| 1.4 | NOTE | Trading-data screens (markets…alerts) are honest `Unavailable` states because the backend exposes no trading-data endpoints. This is the correct §7/§49 behavior, not "empty pages to fill nav" — each explains the exact missing boundary. | Accepted + documented. |
| 1.5 | OK | Design-system primitives are centralized in `src/components/ui/` and reused; no page-specific duplicate components. | Accepted (§44). |

**Verdict:** PASS — 0 BLOCKER / 0 MAJOR / 0 MINOR / 2 NOTE (1 fixed, 1 documented).

---

## Review 2 — Runtime / API Integration

**Scope:** REST, WebSocket, auth lifecycle, errors, pagination, reconnect, stale state.

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 2.1 | OK | REST client parses the backend structured error envelope `{ error: { code, message, request_id, details } }` and throws a normalized `ApiError` (status/code/requestId); non-envelope bodies fall back to a generic error, never echoed raw. | Tests `errors.test.ts`. |
| 2.2 | OK | Auth lifecycle implemented: login → session → `/me`; refresh on expired access token during restore; logout clears in-memory session; 401/403 handled. | `auth-context.tsx` + `session-store.test.ts`. |
| 2.3 | OK | WebSocket client authenticates with the token query param, normalizes/validates events to the known `HEALTH_UPDATE` shape (drops unknown/malformed), and reconnects with bounded backoff; user-triggered close stops reconnection. | Tests `ws-client.test.ts`. |
| 2.4 | OK | Staleness is tracked on system polling (last-success timestamp vs threshold) and surfaced in the Dashboard ("Data may be stale"). | `use-system.ts`. |
| 2.5 | NOTE | **No pagination is implemented** because the only list-like data exposed (none) has no endpoint yet. Pagination will be wired when order/position endpoints exist (§17). | Documented as deferred, not fabricated. |
| 2.6 | NOTE | **Live backend E2E deferred** — no Docker/PostgreSQL, so `/auth/login`/`/auth/me` cannot serve. Contract shapes are verified by mirroring Pydantic schemas + unit tests; this is not "mocked API as the only evidence" (§37), it is the environment's hard boundary. | Documented honestly. |

**Verdict:** PASS — 0 BLOCKER / 0 MAJOR / 0 MINOR / 2 NOTE (documented deferred items).

---

## Review 3 — UX / Financial Correctness

**Scope:** correct numbers/status, no stale/fake data, no double display, honest unavailable states.

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 3.1 | OK | Dashboard renders only **real** backend values: `service`, `api`/`database`/`broker` readiness checks, `live_trading`. No value is invented. | `dashboard/page.tsx`. |
| 3.2 | OK | Trading metrics (portfolio value, cash, exposure, P&L, risk, etc.) show **Unavailable**, never `0`, because no backend meaning exists yet (§10). | Test `data-unavailable.test.tsx` asserts no fake `0`. |
| 3.3 | OK | Status is never color-only: every indicator is dot **+** text label (connection, staleness, mode). | `status-indicator.tsx`. |
| 3.4 | OK | Loading (skeleton), empty (explicit `EmptyState`), and error (`ErrorState` with retry) states are present; no fabricated zero-value financial data while loading (§30/§31). | `dashboard`, `(app)/loading.tsx`, `error.tsx`, `not-found.tsx`. |
| 3.5 | OK | No authoritative math in the browser: the frontend renders backend values only; no P&L/position/risk recalculation (§56). | Design. |

**Verdict:** PASS — 0 BLOCKER / 0 MAJOR / 0 MINOR / 0 NOTE.

---

## Review 4 — Security / LIVE Safety

**Scope:** token handling, XSS, permissions, broker-credential isolation, direct broker/DB access, LIVE bypass.

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 4.1 | OK | **Tokens in memory only** — never localStorage/sessionStorage/cookies/IndexedDB; never logged. The backend returns JSON tokens and sets no httpOnly cookie, so in-memory is the correct (safest available) mechanism (§5/§42). | `session-store.ts` + `README.md`. |
| 4.2 | OK | **No LIVE bypass**: `resolveTradingMode` maps only `"enabled"` → LIVE; `"disabled"`/unknown → PAPER/UNKNOWN (fail-closed). The badge is read-only with no toggle. Tested that LIVE never renders for a disabled backend. | `trading-mode.ts` + `trading-mode.test.ts` + `trading-mode-badge.test.tsx`. |
| 4.3 | OK | **No broker/DB access from browser**: all network calls go through the centralized REST client → `API_BASE_URL` → backend; there is no broker SDK, no SQL, no direct vendor call anywhere in `src/`. Broker credentials never reach the browser. | Architecture + README. |
| 4.4 | OK | **No XSS surface**: React escapes by default; no `dangerouslySetInnerHTML` anywhere; WebSocket/JSON inputs are type-validated before use. | Code audit. |
| 4.5 | OK | **RBAC is not UI-only**: the shell requires `system:read`, trading areas require `trading:view`; server 401/403 is still the authority and is handled everywhere (login failure, session expiry → refresh/redirect). | `require-auth.tsx`, `permissions.ts`. |
| 4.6 | OK | **No secrets in frontend env**: only `NEXT_PUBLIC_API_BASE_URL`/`NEXT_PUBLIC_WS_URL` (public URLs); `.env` is gitignored; `env.ts` centralizes reads so no ad hoc `process.env` leaks. | `env.ts`, `.env.example`, `.gitignore`. |

**Verdict:** PASS — 0 BLOCKER / 0 MAJOR / 0 MINOR / 0 NOTE.

---

## Summary

- **0 BLOCKER / 0 MAJOR / 0 MINOR / 4 NOTE (1 fixed — Next.js security upgrade; 3 documented — honest deferred scope).**
- All legitimate findings were fixed (Next.js 14.2.5 → 14.2.35 for the security advisory); regression via clean `npm install`, `npm test`, `npm run build`.
- **DEFERRED (honest)**: live backend E2E (no Docker/PostgreSQL), trading-data screens (no backend endpoints), pagination (no list endpoints), TradingView Lightweight Charts (no chart data endpoint).
- **No independent reviewer is claimed** — this is an inline adversarial review, transparently recorded.
