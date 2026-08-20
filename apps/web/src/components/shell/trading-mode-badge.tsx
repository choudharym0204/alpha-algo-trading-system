import { Badge } from "@/components/ui/badge";
import { resolveTradingMode, LIVE_BLOCKED_REASON } from "@/lib/trading-mode";

/**
 * Authoritative trading-mode badge. Reflects the backend `live_trading` signal
 * only — it has no toggle and cannot enable LIVE (spec §9 / §41).
 */
export function TradingModeBadge({ liveTrading }: { liveTrading: string | null | undefined }) {
  const mode = resolveTradingMode(liveTrading);
  if (mode === "LIVE") {
    return <Badge variant="danger">LIVE</Badge>;
  }
  if (mode === "PAPER") {
    return (
      <span title={LIVE_BLOCKED_REASON}>
        <Badge variant="info">PAPER</Badge>
      </span>
    );
  }
  return <Badge variant="warn">MODE UNKNOWN</Badge>;
}
