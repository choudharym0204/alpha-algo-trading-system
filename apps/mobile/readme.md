# Alpha Algo Mobile — Trading Terminal (Phase 18)

Production-grade **Flutter** mobile foundation for the Alpha Algo Trading System.
The app is a presentation/control layer only: it connects to the backend through
authenticated REST + WebSocket and never touches PostgreSQL, Redis, broker APIs,
broker SDKs, broker credentials, execution adapters, or internal service databases.

## Honest scope (Phase 18)

The backend currently exposes **only** auth + system + WebSocket:

| Backend contract | Method | Path | Wired in mobile? |
|---|---|---|---|
| Login | `POST` | `/api/v1/auth/login` | ✅ |
| Refresh | `POST` | `/api/v1/auth/refresh` | ✅ |
| Current user | `GET` | `/api/v1/auth/me` | ✅ |
| Health | `GET` | `/api/v1/system/health` | ✅ |
| Readiness | `GET` | `/api/v1/system/ready` | ✅ |
| WebSocket health | `WS` | `/api/v1/ws?token=***` | ✅ |

There are **no** trading-data endpoints yet (orders, positions, portfolio, P&L,
strategies, risk, brokers, reconciliation, market data, watchlist). Every such
screen renders an explicit **Unavailable** state — never fabricated zeros or mock
data (spec §2 / §55).

## Stack

- **Flutter** (Dart 3, strict null safety)
- State management: **Provider** (ChangeNotifier) — no duplicate systems
- HTTP: `http` · Secure storage: `flutter_secure_storage` · WS: `web_socket_channel`

## Run (requires Flutter SDK)

> ⚠️ This environment has **no Flutter SDK**, so platform folders (`android/`,
> `ios/`, etc.) are NOT committed. Generate them on a Flutter-equipped machine:

```bash
cd apps/mobile
flutter create --org com.alphaalgo --project-name alpha_algo_mobile .
flutter pub get
flutter run            # Android emulator / device
```

Point at the backend for a physical device:

```bash
flutter run --dart-define=API_BASE_URL=http://192.168.1.10:8000 \
            --dart-define=WS_URL=ws://192.168.1.10:8000
```

Verify:

```bash
flutter analyze        # static analysis
flutter test           # unit + widget tests
flutter build apk --debug
```

## Architecture

```
lib/
├── main.dart / app.dart        # composition root + provider wiring + root gate
├── config/app_config.dart      # env (API/WS URLs) via --dart-define
├── core/                       # api_error, trading_mode, permissions
├── models/                     # auth / system / ws typed models
├── network/api_client.dart     # typed REST + error envelope
├── auth/                       # token_store, session, repository, controller
├── websocket/                  # ws_client + ws_controller (reconnect + validation)
├── repositories/               # system_repository + system_controller (poll)
├── features/                   # auth / shell / home / more
└── widgets/                    # design system + unavailable_view
```

Flow: **Presentation → State (ChangeNotifier) → Repository → API/WS Client → Backend**.
No API/business logic inside widgets.

## Key decisions

- **Tokens in secure storage** — `flutter_secure_storage` (Android Keystore / iOS
  Keychain backed). Never plain shared preferences, never logged.
- **Backend is the security boundary** — RBAC in the UI only hides screens;
  server 401/403 is always handled. `system:read` gates the shell, `trading:view`
  gates trading screens.
- **LIVE is fail-closed** — `resolveTradingMode("disabled")` → PAPER; only
  `"enabled"` → LIVE; anything else → UNKNOWN (never LIVE). No enable-LIVE switch.
- **No authoritative math in Dart** — the app renders backend values only.
  Unavailable metrics show "Unavailable", not `0`.
- **Offline = read-only + clear offline state** — no offline order queuing.

## Testing

- `test/core/api_error_test.dart` — error-envelope parsing + classification
- `test/core/trading_mode_test.dart` — fail-closed PAPER/LIVE derivation
- `test/core/permissions_test.dart` — RBAC gating
- `test/auth/session_test.dart` — token expiry skew
- `test/models/ws_models_test.dart` — typed WS event validation
- `test/widgets/trading_mode_badge_test.dart` — LIVE never shown when disabled
- `test/widgets/unavailable_view_test.dart` — honest boundary, no fake zeros
- `test/widgets/login_screen_test.dart` — form validation

## LIVE safety summary

- `LIVE_TRADING_ENABLED = false`, `GLOBAL_TRADING_HALT = true` (backend).
- UI reflects these; no fake LIVE controls; no frontend bypass; PAPER never maps
  to a live broker path.
- Broker credentials, API secrets, and tokens never reach the app binary.

## Known limitations (honest)

- **Platform folders not generated** — this environment has no Flutter SDK;
  run `flutter create .` (above) to generate `android/`/`ios/`.
- **Verification deferred** — `flutter analyze` / `flutter test` / `flutter build`
  were NOT run (no Flutter SDK / Android SDK / Java). Source + tests are complete
  and ready to run on a Flutter machine.
- **Live backend E2E deferred** — no Docker/PostgreSQL, so `/auth/login`/`/auth/me`
  cannot serve against a real DB. Contract shapes mirror the backend Pydantic
  schemas; full E2E is VERIFIED/PRODUCTION-time work.
- **Trading data not wired** — no backend trading-data endpoints; screens are
  honest Unavailable states.
