import { apiRequest } from "./client";
import type { HealthResponse, ReadinessResponse } from "./types";

/** GET /api/v1/system/health (public). */
export function health(): Promise<HealthResponse> {
  return apiRequest<HealthResponse>("/api/v1/system/health");
}

/** GET /api/v1/system/ready (public). */
export function readiness(): Promise<ReadinessResponse> {
  return apiRequest<ReadinessResponse>("/api/v1/system/ready");
}
