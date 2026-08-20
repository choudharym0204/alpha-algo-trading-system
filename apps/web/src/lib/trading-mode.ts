/**
 * Trading-mode derivation from backend-authoritative signals.
 *
 * The browser NEVER decides LIVE vs PAPER itself. The backend `/health` (and
 * the WebSocket HEALTH_UPDATE) expose `live_trading` as the authoritative
 * signal. The frontend only reflects it — it cannot toggle it.
 */

export type TradingMode = "PAPER" | "LIVE" | "UNKNOWN";

export const LIVE_BLOCKED_REASON =
  "Live trading is disabled by the backend (LIVE_TRADING_ENABLED=false, GLOBAL_TRADING_HALT=true).";

/**
 * Resolve the display trading mode from the backend `live_trading` value.
 *
 * Fail-closed: "disabled" (and anything unknown) resolves to PAPER, never LIVE.
 * LIVE is only ever shown when the backend explicitly reports "enabled".
 */
export function resolveTradingMode(liveTrading: string | null | undefined): TradingMode {
  if (liveTrading === "enabled") return "LIVE";
  if (liveTrading === "disabled") return "PAPER";
  return "UNKNOWN";
}

export function isLiveTradingEnabled(liveTrading: string | null | undefined): boolean {
  return liveTrading === "enabled";
}
