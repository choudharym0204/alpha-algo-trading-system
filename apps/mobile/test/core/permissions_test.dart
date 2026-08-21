import 'package:flutter_test/flutter_test.dart';
import 'package:alpha_algo_mobile/core/permissions.dart';

void main() {
  group('hasPermission', () {
    test('grants when present', () {
      expect(
        hasPermission(const ['system:read', 'trading:view'], Permissions.systemRead),
        isTrue,
      );
    });

    test('denies when absent', () {
      expect(hasPermission(const ['trading:view'], Permissions.liveTrade), isFalse);
    });

    test('denies on null/empty', () {
      expect(hasPermission(null, Permissions.systemRead), isFalse);
      expect(hasPermission(const <String>[], Permissions.systemRead), isFalse);
    });
  });
}
