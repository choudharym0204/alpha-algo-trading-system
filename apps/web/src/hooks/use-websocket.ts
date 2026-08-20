"use client";

import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/context/auth-context";
import { getSession } from "@/lib/auth/session-store";
import type { HealthUpdateEvent } from "@/lib/api/types";
import { createTradingWebSocket, type WsStatus } from "@/lib/ws/client";

interface WebSocketState {
  status: WsStatus;
  lastEvent: HealthUpdateEvent | null;
}

/**
 * Maintains the authenticated /api/v1/ws connection for the current session.
 * Reconnects automatically (bounded backoff) and surfaces connection status +
 * the last normalized HEALTH_UPDATE event.
 */
export function useWebSocket(): WebSocketState {
  const { status: authStatus } = useAuth();
  const [status, setStatus] = useState<WsStatus>("closed");
  const [lastEvent, setLastEvent] = useState<HealthUpdateEvent | null>(null);
  const socketRef = useRef<ReturnType<typeof createTradingWebSocket> | null>(null);

  useEffect(() => {
    if (authStatus !== "authenticated") {
      setStatus("closed");
      return;
    }
    const session = getSession();
    if (!session) return;

    const socket = createTradingWebSocket(session.accessToken, {
      onStatus: setStatus,
      onEvent: setLastEvent,
    });
    socketRef.current = socket;
    socket.connect();

    return () => {
      socket.close();
      socketRef.current = null;
    };
  }, [authStatus]);

  return { status, lastEvent };
}
