import { StatusIndicator, toneFromStatus } from "@/components/ui/status-indicator";
import type { WsStatus } from "@/lib/ws/client";

const statusLabels: Record<WsStatus, string> = {
  connecting: "Connecting",
  open: "Connected",
  closed: "Disconnected",
  reconnecting: "Reconnecting",
};

/** WebSocket connection status — dot + text (never color-only). */
export function ConnectionIndicator({ status }: { status: WsStatus }) {
  return <StatusIndicator tone={toneFromStatus(status)} label={statusLabels[status]} />;
}
