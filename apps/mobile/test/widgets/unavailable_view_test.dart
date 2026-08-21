import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:alpha_algo_mobile/features/shell/feature_definitions.dart';
import 'package:alpha_algo_mobile/widgets/unavailable_view.dart';

const _positions = FeatureDefinition(
  id: 'positions',
  title: 'Positions',
  description: 'No position endpoint yet.',
  expectedData: ['Instrument', 'Quantity', 'Unrealized P&L'],
  permission: 'trading:view',
);

void main() {
  group('UnavailableView (honest boundary)', () {
    testWidgets('marks the area Unavailable and lists expected data', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(home: UnavailableView(feature: _positions)),
      );
      expect(find.text('Unavailable'), findsOneWidget);
      expect(find.text('Instrument'), findsOneWidget);
      expect(find.text('Quantity'), findsOneWidget);
      expect(find.text('Unrealized P&L'), findsOneWidget);
    });

    testWidgets('does not render a zero financial value', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(home: UnavailableView(feature: _positions)),
      );
      expect(find.text('0'), findsNothing);
    });
  });
}
