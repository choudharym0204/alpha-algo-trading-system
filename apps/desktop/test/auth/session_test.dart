import 'package:flutter_test/flutter_test.dart';
import 'package:alpha_algo_desktop/auth/session.dart';

void main() {
  group('Session.isAccessTokenUsable', () {
    test('usable before expiry (5s skew)', () {
      final session = Session(
        accessToken: 'a',
        refreshToken: 'r',
        accessExpiresAt: DateTime.now().add(const Duration(seconds: 10)),
      );
      expect(session.isAccessTokenUsable(DateTime.now()), isTrue);
    });

    test('unusable within the skew window', () {
      final session = Session(
        accessToken: 'a',
        refreshToken: 'r',
        accessExpiresAt: DateTime.now().add(const Duration(seconds: 2)),
      );
      expect(session.isAccessTokenUsable(DateTime.now()), isFalse);
    });
  });
}
