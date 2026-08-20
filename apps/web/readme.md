# Alpha Algo Web — Trading Terminal (Phase 17)

Production-grade web terminal built against the **verified backend contracts**. The
browser is a presentation/control layer only: it never touches PostgreSQL, Redis,
broker APIs, broker credentials, or internal service databases.

## Honest scope (Phase 17)

The backend currently exposes **only** the auth + system + WebSocket surface:

| Backend contract | Method | Path | Wired in web? |
|---|---|---|---|
| Login | `POST` | `/api/v1/auth/login` | ✅ |
| Refresh | `POST` | `/api/v1/auth/refresh` | ✅ |
| Current user | `GET` | `/api/v1/auth/me` | ✅ |
| Health | `GET` | `/api/v1/system/health` | ✅ |
| Readiness | `GET` | `/api/v1/system/ready` | ✅ |
| WebSocket health | `WS` | `/api/v1/ws?token=…` | ✅ |

There are **no** trading-data endpoints yet (orders, positions, portfolio, P&L,
strategies, risk, brokers, reconciliation, market data, watchlist). Every such
screen renders an explicit **Unavailable** state — never fabricated zeros or mock
data (spec §7 / §10 / §49).

## Stack

- **Next.js 14** (App Router) + **React 18** + **TypeScript 5** (strict)
- **Tailwind CSS 3**
- Hand-rolled design system (no external UI kit) — see `src/components/ui/`
- **Vitest + React Testing Library** for unit/component tests
- `npm` as package manager

## Run

```bash
cd apps/web
cp .env.example .env.local   # set NEXT_PUBLIC_API_BASE_URL / NEXT_PUBLIC_WS_URL
npm install
npm run dev                  # http://localhost:3000
```

```bash
npm test                     # Vitest (unit + component)
npm run build                # production build + type check
npm start                    # serve production build
```

## Architecture

```
src/
├── app/                     # App Router routes
│   ├── layout.tsx           # root: AuthProvider + ToastProvider
│   ├── page.tsx             # redirect by auth state
│   ├── login/page.tsx       # login form (real backend contract)
│   ├── (app)/layout.tsx     # protected shell (RequireAuth system:read)
│   ├── (app)/dashboard/     # REAL system health/readiness + safety + WS
│   └── (app)/<area>/        # markets…settings (honest Unavailable states)
├── components/
│   ├── ui/                  # design system primitives
│   ├── shell/               # sidebar, topbar, mode badge, connection
│   ├── auth/require-auth.tsx
│   └── data-unavailable.tsx
├── context/auth-context.tsx # login/logout/refresh/me + permission checks
├── hooks/                   # use-system (poll), use-websocket
└── lib/
    ├── api/                 # client, errors, auth, system, types
    ├── auth/                # permissions, session-store (in-memory)
    ├── ws/client.ts         # authenticated WS + reconnect + event validation
    ├── navigation.ts        # nav config (permission-gated)
    └── trading-mode.ts      # PAPER/LIVE derivation (fail-closed)
```

## Key decisions

- **Tokens in memory only** — the backend returns tokens in JSON and sets no
  httpOnly cookie; there is no safer browser-storage mechanism, so tokens are
  never written to localStorage/sessionStorage/cookies/IndexedDB. A full reload
  requires re-authentication (documented, not a bug).
- **Backend is the security boundary** — RBAC in the UI only drives what is
  shown; server 401/403 is always handled. `system:read` gates the shell,
  `trading:view` gates trading areas, `trading:paper`/`trading:live` gate order
  entry (none wired yet).
- **LIVE is fail-closed** — the mode badge reflects `health.live_trading`
  (`"disabled"` → PAPER). There is no UI toggle, no LIVE path, and no bypass.
- **No authoritative math in the browser** — the frontend renders backend values
  only. Unavailable metrics show "Unavailable", not `0`.

## Testing

- `tests/unit/errors.test.ts` — backend error-envelope parsing + safe fallback
- `tests/unit/permissions.test.ts` — RBAC gating
- `tests/unit/session-store.test.ts` — in-memory token lifecycle + expiry skew
- `tests/unit/trading-mode.test.ts` — fail-closed PAPER/LIVE derivation
- `tests/unit/ws-client.test.ts` — typed WebSocket event validation
- `tests/unit/components/trading-mode-badge.test.tsx` — LIVE never shown when disabled
- `tests/unit/components/data-unavailable.test.tsx` — honest boundary, no fake zeros

Live backend E2E (real login against PostgreSQL) is deferred: this environment
has no Docker/PostgreSQL, so the API cannot serve `/auth/login`/`/auth/me`.
Contract shapes are verified by matching the backend Pydantic schemas and by the
unit tests; full live E2E is a VERIFIED/PRODUCTION-time activity.

## LIVE safety summary

- `LIVE_TRADING_ENABLED = false`, `GLOBAL_TRADING_HALT = true` (backend).
- UI reflects these; no fake LIVE controls; no frontend bypass.
- Broker credentials, API secrets, and tokens never reach the browser.
