import 'package:flutter_test/flutter_test.dart';
import 'package:alpha_algo_desktop/core/trading_mode.dart';

void main() {
  group('resolveTradingMode (fail-closed)', () {
    test("maps 'disabled' to paper, never live", () {
      expect(resolveTradingMode('disabled'), TradingMode.paper);
    });

    test("maps 'enabled' to live", () {
      expect(resolveTradingMode('enabled'), TradingMode.live);
    });

    test('maps unknown/missing to unknown, never live', () {
      expect(resolveTradingMode('bogus'), TradingMode.unknown);
      expect(resolveTradingMode(null), TradingMode.unknown);
    });

    test('never enables live for anything but the exact string', () {
      expect(isLiveTradingEnabled('disabled'), isFalse);
      expect(isLiveTradingEnabled('DISABLED'), isFalse);
      expect(isLiveTradingEnabled('1'), isFalse);
      expect(isLiveTradingEnabled('enabled'), isTrue);
    });
  });
}
