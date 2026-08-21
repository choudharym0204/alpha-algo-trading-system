# Phase 19 — Desktop Platform — Session Report

**Date:** 2026-08-21
**Status:** TESTED — analyze 0 issues; 29/29 tests; `flutter build windows` GREEN; Windows runtime E2E GREEN (real backend); backend regression 1611 passed

---

## 1. Objective

Build a professional desktop trading terminal (`apps/desktop/`) for Windows (primary)
and macOS (deferred). The desktop client is a **presentation/control layer** that talks
to the FastAPI backend exclusively through authenticated REST + WebSocket. It never
touches PostgreSQL, Redis, broker APIs/SDKs, broker credentials, or internal service
databases (Phase 19 §1 / §55).

## 2. Technology

- **Flutter Desktop** (Windows + macOS targets), Dart 3.13.1, Flutter 3.47.1.
- Reuses the **Phase 18 mobile client layer** as a mirror under `lib/` (auth, REST client,
  WebSocket client, error/permission/trading-mode models, system repositories).
- State management: `provider` + `ChangeNotifier` (no duplicate systems).
- Secure token storage: `flutter_secure_storage` (Windows DPAPI / macOS Keychain).

## 3. Shared client architecture

The desktop client mirrors the mobile client's non-UI layer verbatim (19 files):
`auth/`, `core/` (permissions, trading-mode, api-error), `models/` (auth/system/ws),
`network/api_client.dart`, `repositories/` (system), `websocket/` (ws client+controller),
and the design primitives (`app_status.dart`, `app_states.dart`).

A formal shared Dart package extraction was **deferred** on purpose: the mobile app is
TESTED, and moving its working code into a package would be a risky refactor without a
third consumer to justify it (Phase 19 §5 "do not move large amounts of working mobile
code solely for theoretical reuse"). The mirror is documented and kept contract-identical.

Desktop-specific code is limited to: shell, navigation, workspace, dashboard, login, and
keyboard shortcuts.

## 4. Backend-first scope (honest)

The backend currently exposes only auth (`/auth/login|refresh|me`), system
(`/system/health|ready`), and an authenticated WebSocket (`/api/v1/ws` → `HEALTH_UPDATE`).
**No trading-data endpoints exist.** Therefore every trading workspace (Markets, Watchlist,
Charts, Orders, Positions, Portfolio, P&L, Strategies, Risk, Brokers, Reconcile, Settings)
renders an honest **Unavailable** state — never fabricated zeros (Phase 19 §4 / §13 / §44).

## 5. Desktop shell

- **Persistent sidebar** (224px): 13 destinations, permission-gated (`system:read` /
  `trading:view`), search filter (Ctrl+K).
- **Top status bar**: brand + section title, `TradingModeBadge` (reflect-only PAPER/LIVE),
  `ConnectionIndicator` (WS state), account subject, sign-out.
- **Workspace area**: dashboard (live) or honest Unavailable panels.
- **Keyboard shortcuts** (safe, no one-key trading): `Ctrl+1` Dashboard, `Ctrl+2` Markets,
  `Ctrl+3` Orders, `Ctrl+4` Positions, `Ctrl+K` search.

## 6. Verification

| Gate | Result |
|------|--------|
| `flutter analyze` | ✅ 0 issues |
| `flutter test` | ✅ **29/29 passed** (10 files) |
| `flutter build windows` | ✅ Release + Debug built (`alpha_algo_desktop.exe`) |
| Windows runtime E2E | ✅ `-d windows` integration test → **All tests passed!** |
| Backend regression | ✅ **1611 passed** |
| macOS build/runtime | ⏳ deferred — no macOS/Xcode |

Windows build originally failed on a real defect: the VS "Desktop development with C++"
workload omitted the **ATL headers** (`atlstr.h`) required by `flutter_secure_storage_windows`.
Fixed by installing `Microsoft.VisualStudio.Component.VC.ATL` into the existing Build
Tools and rebuilding (see `P19-review.md`).

Verification ran on a clean-path copy `C:\src\desktop_verify` because the canonical repo
path `C:\Users\MUKESH'S PC\...` apostrophe breaks Flutter's generated test-listener tooling
(same documented Phase 18 limitation).

## 7. Tests (29)

- **Unit (shared layer):** session, api-error envelope, permissions, trading-mode
  (fail-closed), WS event normalization (typed validation).
- **Widget (desktop):** login (validation + fail-closed messaging), trading-mode badge
  (never LIVE when disabled), unavailable view (no fabricated zero), desktop shell
  (sidebar destinations + navigation + sign-out), dashboard (skeleton/loaded + honest
  unavailable metrics).
- **Integration (Windows E2E, `integration_test/app_e2e_test.dart`):** drives the real
  desktop app against the real PostgreSQL-backed API — login → dashboard → authenticated
  WS `HEALTH_UPDATE` → honest Unavailable → logout → re-login (run `-d windows`).

## 8. Review findings

Inline 4-axis review (Architecture / Runtime / UX-Data-Integrity / Security-LIVE). No
BLOCKER or MAJOR findings. Four MINOR fixes applied during verification: (1) an unused
import in the shell, (2) a misplaced `featureFor` import in a test, (3) a `RenderFlex`
overflow in dashboard metric cards (fixed with `Expanded` + ellipsis), (4) an overly-strict
`PAPER` assertion. See `P19-review.md`.

## 9. Security / LIVE safety

- Tokens in `flutter_secure_storage` (Windows DPAPI), never plaintext.
- No broker credentials, no direct DB/broker access, no authoritative math in Dart.
- `LIVE_TRADING_ENABLED=false`, `GLOBAL_TRADING_HALT=true` remain fail-closed; the mode
  badge reflects the backend signal only and there is **no local LIVE switch**.

## 10. Limitations (documented, not hidden)

- **macOS deferred** — no macOS/Xcode in this environment.
- **No trading-data E2E** — backend exposes no orders/positions/portfolio/P&L/etc. endpoints;
  those panels are honest Unavailable (Phase 19 §39 / §40).
- **Shared-layer mirror (not a package)** — desktop mirrors mobile's non-UI layer; a formal
  shared Dart package extraction is deliberately deferred (§5).
- Phase 20 (Observability) is **not** started.
