import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:alpha_algo_desktop/features/home/dashboard_screen.dart';
import 'package:alpha_algo_desktop/models/system_models.dart';
import 'package:alpha_algo_desktop/network/api_client.dart';
import 'package:alpha_algo_desktop/repositories/system_controller.dart';
import 'package:alpha_algo_desktop/repositories/system_repository.dart';
import 'package:alpha_algo_desktop/websocket/ws_controller.dart';
import 'package:alpha_algo_desktop/widgets/design/app_states.dart';

class _FakeSystemRepository extends SystemRepository {
  _FakeSystemRepository() : super(ApiClient());

  @override
  Future<HealthStatus> health() async => const HealthStatus(
        service: 'alpha-algo-api',
        status: 'ok',
        liveTrading: 'disabled',
      );

  @override
  Future<ReadinessStatus> readiness() async => const ReadinessStatus(
        service: 'alpha-algo-api',
        status: 'ready',
        liveTrading: 'disabled',
        checks: {'api': 'ok', 'database': 'ok', 'broker': 'disabled'},
      );
}

Widget _wrap(SystemController system, WsController ws) {
  return MultiProvider(
    providers: [
      ChangeNotifierProvider<SystemController>.value(value: system),
      ChangeNotifierProvider<WsController>.value(value: ws),
    ],
    child: const MaterialApp(home: Scaffold(body: DashboardScreen())),
  );
}

void main() {
  testWidgets('shows skeletons while loading', (tester) async {
    final system = SystemController(_FakeSystemRepository());
    await tester.pumpWidget(_wrap(system, WsController()));
    await tester.pump();
    expect(find.byType(AppSkeleton), findsWidgets);
  });

  testWidgets('shows real health/readiness and honest unavailable metrics', (tester) async {
    final system = SystemController(_FakeSystemRepository());
    await system.refresh();
    await tester.pumpWidget(_wrap(system, WsController()));
    await tester.pump();

    // Dense stat cards (labels are uppercased).
    expect(find.text('SERVICE'), findsOneWidget);
    expect(find.text('DATABASE'), findsOneWidget);
    expect(find.text('BROKER'), findsOneWidget);
    expect(find.text('ok'), findsWidgets);

    // Safety + PAPER (fail-closed) + real-time gateway.
    expect(find.text('Trading safety'), findsOneWidget);
    expect(find.text('PAPER'), findsWidgets);
    expect(find.text('Real-time gateway'), findsOneWidget);

    // Trading metrics are Unavailable, never a fabricated zero.
    expect(find.text('Unavailable'), findsWidgets);
    expect(find.text('0'), findsNothing);
  });
}
