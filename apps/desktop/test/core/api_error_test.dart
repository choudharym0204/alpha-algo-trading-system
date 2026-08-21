import 'package:flutter_test/flutter_test.dart';
import 'package:alpha_algo_desktop/core/api_error.dart';

void main() {
  group('parseApiError', () {
    test('parses the backend structured envelope', () {
      final error = parseApiError(401, {
        'error': {
          'code': 'AUTH_REQUIRED',
          'message': 'Authentication required.',
          'request_id': 'abc-123',
          'details': <String, dynamic>{},
        },
      });
      expect(error.status, 401);
      expect(error.code, 'AUTH_REQUIRED');
      expect(error.message, 'Authentication required.');
      expect(error.requestId, 'abc-123');
      expect(error.isUnauthorized, isTrue);
    });

    test('falls back safely on a non-envelope body', () {
      final error = parseApiError(502, '<html>Bad Gateway</html>');
      expect(error.code, 'UNEXPECTED_RESPONSE');
      expect(error.requestId, 'unknown');
    });

    test('classifies 403 as forbidden and 429 as rate-limited', () {
      final forbidden = parseApiError(403, {
        'error': {'code': 'FORBIDDEN', 'message': 'denied', 'request_id': 'r'},
      });
      final rateLimited = parseApiError(429, {
        'error': {'code': 'RATE_LIMITED', 'message': 'slow down', 'request_id': 'r'},
      });
      expect(forbidden.isForbidden, isTrue);
      expect(rateLimited.isRateLimited, isTrue);
    });
  });
}
