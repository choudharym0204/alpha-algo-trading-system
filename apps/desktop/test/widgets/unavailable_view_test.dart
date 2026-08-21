import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:alpha_algo_desktop/features/shell/navigation.dart';
import 'package:alpha_algo_desktop/widgets/unavailable_view.dart';

void main() {
  testWidgets('marks the area Unavailable and lists expected data', (tester) async {
    final feature = featureFor('orders')!;
    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: UnavailableView(feature: feature))),
    );
    expect(find.text('Unavailable'), findsOneWidget);
    expect(find.text('Orders'), findsOneWidget);
    expect(find.text('No data shown as zero'), findsOneWidget);
    expect(find.text('Avg fill price'), findsOneWidget);
  });

  testWidgets('does not render a zero financial value', (tester) async {
    final feature = featureFor('portfolio')!;
    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: UnavailableView(feature: feature))),
    );
    expect(find.text('0'), findsNothing);
    expect(find.text(r'$0'), findsNothing);
    expect(find.text('0.00'), findsNothing);
  });
}
