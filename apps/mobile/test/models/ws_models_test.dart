import 'package:flutter_test/flutter_test.dart';
import 'package:alpha_algo_mobile/models/ws_models.dart';

void main() {
  group('normalizeWsEvent (typed event model)', () {
    test('accepts a valid HEALTH_UPDATE', () {
      final event = normalizeWsEvent(
        '{"type":"HEALTH_UPDATE","payload":{"service":"alpha-algo","status":"ok","live_trading":"disabled"}}',
      );
      expect(event, isNotNull);
      expect(event!.service, 'alpha-algo');
      expect(event.status, 'ok');
      expect(event.liveTrading, 'disabled');
    });

    test('rejects unknown event types', () {
      expect(normalizeWsEvent('{"type":"ORDER_FILL","payload":{}}'), isNull);
    });

    test('rejects malformed payloads', () {
      expect(
        normalizeWsEvent('{"type":"HEALTH_UPDATE","payload":{"status":"ok"}}'),
        isNull,
      );
      expect(
        normalizeWsEvent(
          '{"type":"HEALTH_UPDATE","payload":{"service":1,"status":"ok","live_trading":"disabled"}}',
        ),
        isNull,
      );
    });

    test('rejects non-JSON / non-string input', () {
      expect(normalizeWsEvent('not json'), isNull);
      expect(normalizeWsEvent(42), isNull);
      expect(normalizeWsEvent(null), isNull);
    });
  });
}
