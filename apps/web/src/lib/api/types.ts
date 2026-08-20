/**
 * TypeScript mirror of the backend Pydantic contracts (apps/api/.../schemas + auth.py).
 *
 * These types are hand-maintained to match the backend exactly. They are NOT
 * generated from OpenAPI yet; when schema generation is wired, these become the
 * generated output. Runtime payloads are still validated defensively at the
 * boundary (see api/client.ts) — TypeScript types are compile-time only.
 */

export type Permission =
  | "system:read"
  | "trading:view"
  | "trading:paper"
  | "trading:live";

/** Uniform backend error envelope: { error: { code, message, request_id, details } }. */
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    request_id: string;
    details?: Record<string, unknown>;
  };
}

/** POST /api/v1/auth/login and /api/v1/auth/refresh response. */
export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_in: number;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RefreshRequest {
  refresh_token: string;
}

/** GET /api/v1/auth/me response. */
export interface CurrentUserResponse {
  subject: string;
  permissions: Permission[];
}

/** GET /api/v1/system/health response. */
export interface HealthResponse {
  service: string;
  status: string;
  live_trading: string;
}

/** GET /api/v1/system/ready response. */
export interface ReadinessResponse extends HealthResponse {
  checks: Record<string, string>;
}

/** WebSocket event emitted by /api/v1/ws. */
export interface HealthUpdateEvent {
  type: "HEALTH_UPDATE";
  payload: {
    service: string;
    status: string;
    live_trading: string;
  };
}
