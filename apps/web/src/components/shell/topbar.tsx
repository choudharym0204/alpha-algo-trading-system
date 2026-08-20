"use client";

import { useAuth } from "@/context/auth-context";
import { useSystem } from "@/hooks/use-system";
import { useWebSocket } from "@/hooks/use-websocket";
import { Button } from "@/components/ui/button";
import { ConnectionIndicator } from "./connection-indicator";
import { TradingModeBadge } from "./trading-mode-badge";

export function Topbar() {
  const { user, logout } = useAuth();
  const { health } = useSystem();
  const { status: wsStatus } = useWebSocket();

  return (
    <header className="flex h-14 items-center justify-between border-b border-surface-border bg-surface px-4">
      <div className="flex items-center gap-4">
        <TradingModeBadge liveTrading={health?.live_trading} />
        <ConnectionIndicator status={wsStatus} />
      </div>
      <div className="flex items-center gap-3">
        {user ? <span className="text-sm text-muted">{user.subject}</span> : null}
        <Button variant="outline" onClick={logout}>
          Sign out
        </Button>
      </div>
    </header>
  );
}
