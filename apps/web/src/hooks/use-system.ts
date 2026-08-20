"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { health, readiness } from "@/lib/api/system";
import type { HealthResponse, ReadinessResponse } from "@/lib/api/types";

const POLL_INTERVAL_MS = 15000;
const STALE_AFTER_MS = 45000;

interface SystemState {
  health: HealthResponse | null;
  readiness: ReadinessResponse | null;
  loading: boolean;
  error: string | null;
  isStale: boolean;
  refresh: () => void;
}

/**
 * Polls the backend system health/readiness endpoints (public, no auth).
 * Tracks staleness so the dashboard never implies freshness when polling has
 * gone quiet (spec §28/§30).
 */
export function useSystem(): SystemState {
  const [healthData, setHealthData] = useState<HealthResponse | null>(null);
  const [readinessData, setReadinessData] = useState<ReadinessResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isStale, setIsStale] = useState(false);
  const lastSuccess = useRef(0);

  const load = useCallback(async () => {
    try {
      const [h, r] = await Promise.all([health(), readiness()]);
      setHealthData(h);
      setReadinessData(r);
      setError(null);
      lastSuccess.current = Date.now();
      setIsStale(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load system status.");
      setIsStale(Date.now() - lastSuccess.current > STALE_AFTER_MS);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const interval = setInterval(() => {
      void load();
      setIsStale(Date.now() - lastSuccess.current > STALE_AFTER_MS);
    }, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [load]);

  return {
    health: healthData,
    readiness: readinessData,
    loading,
    error,
    isStale,
    refresh: load,
  };
}
