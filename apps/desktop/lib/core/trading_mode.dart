/// Trading-mode derivation from backend-authoritative signals.
///
/// The mobile app NEVER decides PAPER vs LIVE itself. The backend `/health`
/// (and the WebSocket HEALTH_UPDATE) expose `live_trading` as the only
/// authoritative signal; the UI only reflects it.
enum TradingMode { paper, live, unknown }

const String liveBlockedReason =
    'Live trading is disabled by the backend '
    '(LIVE_TRADING_ENABLED=false, GLOBAL_TRADING_HALT=true).';

/// Resolve the display trading mode from the backend `live_trading` value.
///
/// Fail-closed: `disabled` (and anything unknown) resolves to `paper`, never
/// `live`. LIVE is only ever shown when the backend reports `enabled`.
TradingMode resolveTradingMode(String? liveTrading) {
  if (liveTrading == 'enabled') return TradingMode.live;
  if (liveTrading == 'disabled') return TradingMode.paper;
  return TradingMode.unknown;
}

bool isLiveTradingEnabled(String? liveTrading) => liveTrading == 'enabled';
