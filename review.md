# Phase 18 — Mobile Platform — Adversarial Review

**Date:** 2026-08-20 (written) / 2026-08-21 (executed verification)
**Backend baseline:** 1611 tests passing (Phases 1–17), re-run and confirmed
**Mobile:** source + 8 test files; **now executed** — `flutter analyze` 0 issues, `flutter test` 23/23, debug + release APK built, installed and launched on a real Pixel 6 / Android 16
**Review method:** No external review subagents are available at the model/provider layer. This review was performed **inline** by the implementing agent and is recorded transparently; it does **not** claim independent reviewer separation. Every legitimate finding below was fixed where possible, or recorded as a documented environment limitation.

---

## Review 1 — Mobile Architecture

**Scope:** structure, state management, repository boundaries, maintainability, dependency policy.

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 1.1 | NOTE | **Flutter SDK is not installed**, so `apps/mobile/` has no generated `android/`/`ios/` platform folders and the app cannot be analyzed/built here. | Documented in README + P18 report; `flutter create .` regenerates platform folders on a Flutter machine. |
| 1.2 | OK | Single state-management system (`provider` + `ChangeNotifier`) — no duplicate systems (spec §3). | Accepted. |
| 1.3 | OK | Clear layering: Presentation → Controller → Repository → ApiClient/WsClient → Backend. No API/business logic inside widgets. | Accepted (§3). |
| 1.4 | OK | Minimal dependencies: `provider`, `http`, `flutter_secure_storage`, `web_socket_channel`, `intl`. No chart/cosmetic-only packages (§49). | Accepted. |
| 1.5 | MINOR | Initial `ws_models.dart` draft contained an over-indirected JSON-decode seam that would not compile (`_convert` referenced but never imported). | FIXED — rewritten to a direct `dart:convert` `jsonDecode`. |

**Verdict:** PASS — 0 BLOCKER / 0 MAJOR / 1 MINOR (fixed) / 1 NOTE (environment).

---

## Review 2 — Runtime / API / WebSocket

**Scope:** auth, refresh, connectivity, reconnect, typed events, stale state, error handling.

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 2.1 | OK | `ApiClient` parses the backend structured error envelope and throws a normalized `ApiError` (status/code/requestId); non-envelope bodies fall back to a generic error; timeout + SocketException + ClientException → `NETWORK_*` (status 0). No blind retry of mutations (§28). | Tests `api_error_test.dart`. |
| 2.2 | OK | Auth lifecycle: login → secure store → `/me`; restore refreshes an expired access token via refresh token; logout clears secure storage; 401/403 handled (§6). | `auth_controller.dart`. |
| 2.3 | OK | WebSocket: token query param, `normalizeWsEvent` drops unknown/malformed payloads, bounded-backoff reconnect, user-close stops reconnect (§26/§27). | `ws_client.dart` + `ws_models_test.dart`. |
| 2.4 | OK | System polling tracks staleness (15s poll, 45s stale threshold) so the dashboard never implies freshness after polling goes quiet (§29). | `system_controller.dart`. |
| 2.5 | NOTE | **None of the above is executed** — no Flutter SDK. Correctness is asserted by careful code review + unit-test source only. | Documented honestly; NOT claimed as verified. |

**Verdict:** PASS — 0 BLOCKER / 0 MAJOR / 0 MINOR / 1 NOTE (verification deferred).

---

## Review 3 — UX / Financial Correctness

**Scope:** no fake numbers, no stale-as-live, correct mode, correct permissions, correct backend mapping.

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 3.1 | OK | Dashboard renders only real backend values (`service`, `api`/`database`/`broker` readiness checks, `live_trading`). Trading metrics show **Unavailable**, never `0` (§12/§55). | `dashboard_screen.dart`. |
| 3.2 | OK | Status is never color-only: badge/dot always carry text labels (§35). | `app_status.dart`. |
| 3.3 | OK | Loading (skeleton) / empty / error (retry) states are present (§37). | `app_states.dart`. |
| 3.4 | OK | No authoritative math in Dart — no P&L/position/portfolio/risk recalculation (§41). | Design. |
| 3.5 | OK | Navigation gated on permissions (`system:read` shell, `trading:view` trading tabs); backend 401/403 remains authoritative (§8/§39). | `app_shell.dart` + `feature_definitions.dart`. |
| 3.6 | NOTE | Widget tests for shell/dashboard navigation exist only for badge/unavailable/login; full shell/dashboard widget-test coverage deferred until Flutter is available to iterate provider wiring. | Documented. |

**Verdict:** PASS — 0 BLOCKER / 0 MAJOR / 0 MINOR / 1 NOTE (coverage deferred).

---

## Review 4 — Security / LIVE Safety

**Scope:** token storage, TLS, logging, secret exposure, direct broker/DB access, LIVE bypass, Paper/Live isolation.

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 4.1 | OK | Tokens in `flutter_secure_storage` (Keystore/Keychain backed); never plain shared preferences, never logged, never in unencrypted files (§7/§38). | `token_store.dart`. |
| 4.2 | OK | **No LIVE bypass**: `resolveTradingMode` maps only `"enabled"` → LIVE; `"disabled"`/unknown → PAPER/UNKNOWN. Badge is read-only; no enable-LIVE switch (§11/§40). Tested by `trading_mode_test.dart` + `trading_mode_badge_test.dart`. |
| 4.3 | OK | No broker/DB access from the app: all network goes through `ApiClient` → backend base URL; no broker SDK, no SQL, no vendor feed (§2). | Architecture. |
| 4.4 | OK | No secrets in the app: only `--dart-define` URLs; no embedded keys; `.env` gitignored (§38). | `app_config.dart`. |
| 4.5 | OK | No `print`/debug token logging (`avoid_print` lint enabled); no `dangerouslySetInnerHTML`-style raw rendering (N/A in Flutter — widgets escape by default). | `analysis_options.yaml`. |
| 4.6 | NOTE | TLS verification is not weakened anywhere; `http` uses platform TLS. Full certificate-pinning review remains a PRODUCTION-time activity. | Documented. |

**Verdict:** PASS — 0 BLOCKER / 0 MAJOR / 0 MINOR / 1 NOTE (TLS hardening deferred to production).

---

## Summary

- **0 BLOCKER / 0 MAJOR / 1 MINOR (fixed) / 4 NOTE (documented).**
- The single MINOR (a compile-broken JSON-decode seam in `ws_models.dart`) was fixed.
- **Executable verification (2026-08-21):** the toolchain (Flutter 3.47.1, Dart 3.13.1, JDK 17, Android SDK 36) was installed and every runnable gate executed: `flutter analyze` → **0 issues**; `flutter test` → **23/23 passed**; `flutter build apk --debug` → `app-debug.apk` (158 MB); `flutter build apk --release` → `app-release.apk` (48.4 MB); installed + launched on a **real Pixel 6 / Android 16** with no crash (PID running, `MainActivity` resumed, no `E/flutter`/`FATAL`). Backend regression **1611 passed**. Secret/fake-data scan **clean**.
- **Verification fixes applied this pass:** 4 `prefer_const_*` analyzer infos fixed properly (no suppression). `flutter create` regenerated platform folders (`android/`, `ios/`, …) and added standard `cupertino_icons` + `flutter_lints` deps plus an `analyzer.exclude` for build/platform dirs; existing `lib/`/`test/` and `pubspec.yaml` dependencies were preserved.
- **Honest environment findings:** (1) the repo path `C:\Users\MUKESH'S PC\…` contains an apostrophe that breaks Flutter's generated test-listener/Gradle tooling — verification ran on a byte-identical clean-path copy at `C:\src\mobile_verify` (relocate the repo to a space/apostrophe-free path eventually). (2) Device-side E2E login → dashboard → WebSocket was **resolved on 2026-08-21**: PostgreSQL 17 provisioned locally, auth/RBAC migrations applied, a test user seeded (argon2id, `system:read` + `trading:view`), the API started against the real DB, and a real-device integration test (`apps/mobile/integration_test/app_e2e_test.dart`) passed on the Pixel 6 (login → dashboard → PAPER → WS `status: connected` → Database `ok` → logout → re-login). (3) The WS "403" was **root-caused** as standard ASGI behavior (the route's `close(1008)` before `accept()` is surfaced by uvicorn as HTTP 403) — not a defect; the authenticated WS path (valid token → `HEALTH_UPDATE` `live_trading: disabled`) is verified working.
- **Final E2E remediation (2026-08-21):** real PostgreSQL auth (`POST /auth/login` 200 → `POST /auth/refresh` 200 → `GET /auth/me` 200 with expected permissions; negative 401 no-token/bad-token, 403 insufficient-permission, 401 wrong-password), authenticated WebSocket (`HEALTH_UPDATE` `live_trading: disabled`), and a real-device integration test on the Pixel 6 all passed with real evidence. **Phase 18 → TESTED** (iOS and full TimescaleDB `alembic upgrade head` remain documented non-blocking limitations). LIVE remains fail-closed.
- **No independent reviewer is claimed** — this is an inline adversarial review, transparently recorded.
