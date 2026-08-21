import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'package:alpha_algo_mobile/app.dart';

/// Real-device E2E: drives the actual app against the real backend
/// (PostgreSQL auth + authenticated WebSocket). Run with:
///
///   flutter test integration_test/app_e2e_test.dart -d <device> \
///     --dart-define=API_BASE_URL=http://localhost:8000 \
///     --dart-define=WS_URL=ws://localhost:8000
///
/// Requires: `adb reverse tcp:8000 tcp:8000` and a seeded test user.
///
/// Credentials are TEST-ONLY (a dedicated local E2E user in a local Postgres).
/// They are not production secrets; override via --dart-define in CI.
const _email = String.fromEnvironment('E2E_EMAIL', defaultValue: 'e2e@alphaalgo.test');
const _password = String.fromEnvironment('E2E_PASSWORD', defaultValue: 'AlphaE2E!Test2026');

Future<void> _pumpUntilFound(
  WidgetTester tester,
  Finder finder, {
  Duration timeout = const Duration(seconds: 30),
  String? label,
}) async {
  final deadline = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(deadline)) {
    await tester.pump(const Duration(milliseconds: 300));
    if (finder.evaluate().isNotEmpty) return;
  }
  fail('Timed out waiting for ${label ?? finder.toString()}');
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('login → dashboard → WS → logout → re-login (real backend)',
      (tester) async {
    // Start from a clean session (no persisted token).
    await const FlutterSecureStorage().deleteAll();
    await tester.pumpWidget(const AlphaAlgoApp());
    await _pumpUntilFound(tester, find.text('Sign in'),
        label: 'login screen (Sign in)');

    // 1. Login screen is visible and shows fail-closed messaging.
    expect(find.text('Live trading is disabled by the backend.'), findsOneWidget);

    // 2. Enter credentials.
    await tester.enterText(find.byType(TextFormField).at(0), _email);
    await tester.enterText(find.byType(TextFormField).at(1), _password);
    await tester.tap(find.text('Sign in'));
    await tester.pump();

    // 3. Authenticated shell appears (dashboard).
    await _pumpUntilFound(tester, find.text('Real-time gateway'),
        label: 'dashboard (Real-time gateway)');

    // 4. PAPER mode badge (fail-closed: never LIVE).
    await _pumpUntilFound(tester, find.text('PAPER'), label: 'PAPER badge');

    // 5. Authenticated WebSocket HEALTH_UPDATE arrived.
    await _pumpUntilFound(
      tester,
      find.textContaining('status: connected, live_trading: disabled'),
      label: 'WS HEALTH_UPDATE text',
    );
    expect(find.text('Connected'), findsWidgets);

    // 6. Readiness shows the real database is reachable.
    await _pumpUntilFound(tester, find.text('DATABASE'), label: 'Database stat');
    expect(find.text('ok'), findsWidgets);

    // 7. Logout.
    await tester.tap(find.byTooltip('Sign out'));
    await tester.pump();
    await _pumpUntilFound(tester, find.text('Sign in'),
        label: 'login screen after logout');

    // 8. Re-login.
    await tester.enterText(find.byType(TextFormField).at(0), _email);
    await tester.enterText(find.byType(TextFormField).at(1), _password);
    await tester.tap(find.text('Sign in'));
    await tester.pump();
    await _pumpUntilFound(tester, find.text('Real-time gateway'),
        label: 'dashboard after re-login');
  });
}
