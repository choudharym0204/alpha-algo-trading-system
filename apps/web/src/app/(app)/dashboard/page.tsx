"use client";

import { useSystem } from "@/hooks/use-system";
import { useWebSocket } from "@/hooks/use-websocket";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/ui/error-state";
import { StatusIndicator, toneFromStatus } from "@/components/ui/status-indicator";
import { TradingModeBadge } from "@/components/shell/trading-mode-badge";
import { ConnectionIndicator } from "@/components/shell/connection-indicator";
import { resolveTradingMode, LIVE_BLOCKED_REASON } from "@/lib/trading-mode";

function Stat({
  label,
  value,
  unavailable,
}: {
  label: string;
  value?: string;
  unavailable?: boolean;
}) {
  return (
    <Card>
      <CardContent className="py-3">
        <p className="text-xs uppercase tracking-wide text-muted">{label}</p>
        {unavailable ? (
          <p className="mt-1 text-sm text-slate-500">Unavailable</p>
        ) : (
          <p className="mt-1 text-lg font-semibold text-white">{value}</p>
        )}
      </CardContent>
    </Card>
  );
}

export default function DashboardPage() {
  const { health, readiness, loading, error, isStale, refresh } = useSystem();
  const { status: wsStatus, lastEvent } = useWebSocket();

  if (loading) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 8 }).map((_, index) => (
          <Skeleton key={index} className="h-24" />
        ))}
      </div>
    );
  }

  if (error && !health) {
    return (
      <ErrorState
        title="Unable to reach the trading API"
        message={error}
        action={
          <Button variant="outline" onClick={refresh}>
            Retry
          </Button>
        }
      />
    );
  }

  const mode = resolveTradingMode(health?.live_trading);
  const checks = readiness?.checks ?? {};

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-white">Dashboard</h1>
          <div className="mt-1 flex items-center gap-2">
            <StatusIndicator
              tone={isStale ? "warn" : "ok"}
              label={isStale ? "Data may be stale" : "Live"}
            />
            <ConnectionIndicator status={wsStatus} />
          </div>
        </div>
        <Button variant="outline" onClick={refresh}>
          Refresh
        </Button>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Service" value={health?.status ?? "unknown"} />
        <Stat label="Trading mode" value={mode} />
        <Stat label="API check" value={checks.api ?? "unknown"} />
        <Stat label="Database check" value={checks.database ?? "unknown"} />
      </div>

      <Card>
        <CardHeader
          title="Trading safety"
          action={<TradingModeBadge liveTrading={health?.live_trading} />}
        />
        <CardContent>
          <p className="text-sm text-muted">
            {LIVE_BLOCKED_REASON} This terminal cannot enable live trading, and no UI control can
            override backend safety.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Badge variant="info">live_trading: {health?.live_trading ?? "unknown"}</Badge>
            <Badge variant="neutral">LIVE_TRADING_ENABLED: false</Badge>
            <Badge variant="warn">GLOBAL_TRADING_HALT: true</Badge>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader title="Real-time gateway" />
        <CardContent>
          <div className="flex items-center gap-2">
            <ConnectionIndicator status={wsStatus} />
            {lastEvent ? (
              <span className="text-sm text-muted">
                Last HEALTH_UPDATE — status: {lastEvent.payload.status}, live_trading:{" "}
                {lastEvent.payload.live_trading}
              </span>
            ) : (
              <span className="text-sm text-muted">Awaiting first health event…</span>
            )}
          </div>
        </CardContent>
      </Card>

      <div>
        <h2 className="mb-2 text-sm font-semibold text-white">Trading metrics</h2>
        <p className="mb-3 text-xs text-muted">
          The backend does not yet expose trading data over the authenticated API. Metrics below are
          shown as Unavailable — not zero — until their endpoints exist (spec §10).
        </p>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Stat label="Portfolio value" unavailable />
          <Stat label="Cash / available funds" unavailable />
          <Stat label="Gross exposure" unavailable />
          <Stat label="Net exposure" unavailable />
          <Stat label="Position count" unavailable />
          <Stat label="Realized P&L" unavailable />
          <Stat label="Unrealized P&L" unavailable />
          <Stat label="Daily P&L" unavailable />
          <Stat label="Risk status" unavailable />
          <Stat label="Market-data status" unavailable />
          <Stat label="Reconciliation status" unavailable />
          <Stat label="Broker status" value={checks.broker ?? "unknown"} />
        </div>
      </div>
    </div>
  );
}
