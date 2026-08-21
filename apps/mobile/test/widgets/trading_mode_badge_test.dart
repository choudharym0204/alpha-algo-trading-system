import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:alpha_algo_mobile/widgets/design/app_status.dart';

Widget _wrap(Widget child) =>
    MaterialApp(home: Scaffold(body: Center(child: child)));

void main() {
  group('TradingModeBadge (LIVE-safety)', () {
    testWidgets('shows PAPER for a disabled backend', (tester) async {
      await tester.pumpWidget(_wrap(const TradingModeBadge(liveTrading: 'disabled')));
      expect(find.text('PAPER'), findsOneWidget);
    });

    testWidgets('never renders LIVE when the backend is disabled', (tester) async {
      await tester.pumpWidget(_wrap(const TradingModeBadge(liveTrading: 'disabled')));
      expect(find.text('LIVE'), findsNothing);
    });

    testWidgets('renders LIVE only for the explicit enabled signal', (tester) async {
      await tester.pumpWidget(_wrap(const TradingModeBadge(liveTrading: 'enabled')));
      expect(find.text('LIVE'), findsOneWidget);
    });

    testWidgets('renders MODE UNKNOWN for an unknown signal (not LIVE)', (tester) async {
      await tester.pumpWidget(_wrap(const TradingModeBadge(liveTrading: 'bogus')));
      expect(find.text('MODE UNKNOWN'), findsOneWidget);
      expect(find.text('LIVE'), findsNothing);
    });
  });
}
