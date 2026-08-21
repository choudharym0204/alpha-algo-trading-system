# Alpha Algo — Desktop Trading Terminal (Phase 19)

Flutter desktop client for the Alpha Algo Trading System. It is a **presentation /
control layer** that talks to the FastAPI backend exclusively through authenticated
REST + WebSocket. It never touches PostgreSQL, Redis, broker APIs, broker SDKs, or
broker credentials directly.

## Platform targets

- **Windows** — primary target.
- **macOS** — deferred (no macOS/Xcode in this environment).

## Backend contract (authoritative)

The backend currently exposes only:

- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `GET  /api/v1/auth/me`
- `GET  /api/v1/system/health`
- `GET  /api/v1/system/ready`
- `WS   /api/v1/ws?token=***` → `HEALTH_UPDATE`

There are **no** trading-data endpoints yet, so every trading workspace
(Markets / Watchlist / Charts / Orders / Positions / Portfolio / P&L / Strategies /
Risk / Brokers / Reconcile / Settings) renders an honest **Unavailable** state —
never fabricated zeros.

## Shared client architecture

The desktop client reuses the Phase 18 mobile client layer (auth, REST client,
WebSocket client, error/permission/trading-mode models, system repositories) as a
mirror under `lib/`. Desktop-specific code is limited to the shell, navigation,
workspace, dashboard, and keyboard shortcuts.

## Build prerequisites (Windows)

`flutter build windows` requires Visual Studio Build Tools 2022 with the **Desktop
development with C++** workload **plus the ATL component** (`Microsoft.VisualStudio.Component.VC.ATL`).
The ATL headers (`atlstr.h`) are needed by `flutter_secure_storage_windows` and are
**not** included by the base VCTools workload — without them the build fails with
`error C1083: Cannot open include file: 'atlstr.h'`. To add ATL to an existing install:

```powershell
& "C:\Program Files (x86)\Microsoft Visual Studio\Installer\setup.exe" modify `
  --installPath "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools" `
  --add Microsoft.VisualStudio.Component.VC.ATL --passive --norestart
```

## Run

```bash
flutter config --enable-windows-desktop
flutter pub get
flutter run -d windows
# point at a non-local backend:
flutter run -d windows --dart-define=API_BASE_URL=http://host:8000 --dart-define=WS_URL=ws://host:8000
```

## Verify

```bash
flutter analyze
flutter test
flutter build windows
```

## End-to-end (real backend)

Drives the real desktop app against the real PostgreSQL-backed API (login → dashboard →
authenticated WebSocket → honest Unavailable → logout → re-login). Requires the backend
on `localhost:8000` and a seeded test user:

```bash
flutter test integration_test/app_e2e_test.dart -d windows \
  --dart-define=API_BASE_URL=http://localhost:8000 \
  --dart-define=WS_URL=ws://localhost:8000
```

## Security

- Tokens are stored via `flutter_secure_storage` (Windows DPAPI / macOS Keychain),
  never in plaintext files.
- `LIVE_TRADING_ENABLED=false` and `GLOBAL_TRADING_HALT=true` remain fail-closed;
  the mode badge only reflects the backend signal and there is no local LIVE switch.
- No broker credentials, no direct DB/broker access, no authoritative math in Dart.
