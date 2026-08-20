import { WS_PATH, WS_URL } from "@/lib/env";
import type { HealthUpdateEvent } from "@/lib/api/types";

export type WsStatus = "connecting" | "open" | "closed" | "reconnecting";

export interface TradingWebSocket {
  /** Open the connection (idempotent). */
  connect(): void;
  /** Close and stop reconnecting. */
  close(): void;
}

export interface WsCallbacks {
  onEvent: (event: HealthUpdateEvent) => void;
  onStatus: (status: WsStatus) => void;
}

/**
 * Authenticated WebSocket client for /api/v1/ws.
 *
 * - Connects with the access token as a query param (backend contract).
 * - Normalizes/validates incoming events to the known HEALTH_UPDATE shape;
 *   unknown or malformed messages are dropped (typed event model — spec §35).
 * - Reconnects with bounded linear backoff; no wall-clock sleep beyond the
 *   browser timer, and never on a user-triggered close.
 * - Carries no credentials beyond the token; never logs it.
 */
export function createTradingWebSocket(token: string, callbacks: WsCallbacks): TradingWebSocket {
  let socket: WebSocket | null = null;
  let closed = false;
  let attempt = 0;
  let timer: ReturnType<typeof setTimeout> | null = null;

  const clearTimer = () => {
    if (timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
  };

  const connect = () => {
    if (closed) return;
    if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
      return;
    }
    callbacks.onStatus(attempt === 0 ? "connecting" : "reconnecting");
    const url = `${WS_URL}${WS_PATH}?token=${encodeURIComponent(token)}`;
    try {
      socket = new WebSocket(url);
    } catch {
      scheduleReconnect();
      return;
    }

    socket.onopen = () => {
      attempt = 0;
      callbacks.onStatus("open");
    };

    socket.onmessage = (message) => {
      const event = normalizeWsEvent(message.data);
      if (event) {
        callbacks.onEvent(event);
      }
    };

    socket.onclose = () => {
      callbacks.onStatus("closed");
      scheduleReconnect();
    };

    socket.onerror = () => {
      // onclose follows onerror; nothing to do here beyond let onclose drive state.
    };
  };

  const scheduleReconnect = () => {
    if (closed) return;
    clearTimer();
    const delay = Math.min(1000 * Math.pow(2, attempt), 15000);
    attempt += 1;
    timer = setTimeout(connect, delay);
  };

  return {
    connect,
    close() {
      closed = true;
      clearTimer();
      if (socket) {
        socket.onclose = null;
        socket.close();
        socket = null;
      }
      callbacks.onStatus("closed");
    },
  };
}

export function normalizeWsEvent(raw: unknown): HealthUpdateEvent | null {
  if (typeof raw !== "string") return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (typeof parsed !== "object" || parsed === null) return null;
  const candidate = parsed as { type?: unknown; payload?: unknown };
  if (candidate.type !== "HEALTH_UPDATE") return null;
  if (typeof candidate.payload !== "object" || candidate.payload === null) return null;
  const payload = candidate.payload as { service?: unknown; status?: unknown; live_trading?: unknown };
  if (
    typeof payload.service !== "string" ||
    typeof payload.status !== "string" ||
    typeof payload.live_trading !== "string"
  ) {
    return null;
  }
  return {
    type: "HEALTH_UPDATE",
    payload: {
      service: payload.service,
      status: payload.status,
      live_trading: payload.live_trading,
    },
  };
}
