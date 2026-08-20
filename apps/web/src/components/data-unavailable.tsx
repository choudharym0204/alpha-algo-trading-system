import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";

/**
 * Honest "backend boundary not yet exposed" state.
 *
 * Phase 17 wires ONLY the auth + system-health + WebSocket surface. Trading
 * data (orders, positions, portfolio, P&L, strategies, risk, brokers,
 * reconciliation, market data, watchlist) has no REST/WS endpoint yet. These
 * screens exist as the terminal's navigable skeleton and MUST show this state
 * instead of fabricating zeroes or mock data (spec §7 / §10 / §49).
 */
export function DataUnavailable({
  area,
  description,
  expectedData,
}: {
  area: string;
  description: string;
  expectedData: readonly string[];
}) {
  return (
    <Card>
      <CardHeader
        title={area}
        action={<Badge variant="warn">Unavailable</Badge>}
      />
      <CardContent>
        <p className="text-sm text-muted">{description}</p>
        <p className="mt-3 text-xs uppercase tracking-wide text-muted">
          Expected once the backend exposes this endpoint
        </p>
        <ul className="mt-2 grid grid-cols-1 gap-1 sm:grid-cols-2">
          {expectedData.map((item) => (
            <li key={item} className="flex items-center gap-2 text-sm text-muted">
              <span className="h-1 w-1 rounded-full bg-slate-600" aria-hidden />
              {item}
            </li>
          ))}
        </ul>
        <p className="mt-4 text-xs text-slate-500">
          This area is intentionally not wired: the backend does not yet serve this data over the
          authenticated API. No values here are real — none are shown as zero.
        </p>
      </CardContent>
    </Card>
  );
}
