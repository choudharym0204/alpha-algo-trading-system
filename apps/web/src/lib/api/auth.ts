import { apiRequest } from "./client";
import type { CurrentUserResponse, LoginRequest, RefreshRequest, TokenResponse } from "./types";

/** POST /api/v1/auth/login. */
export function login(payload: LoginRequest): Promise<TokenResponse> {
  return apiRequest<TokenResponse>("/api/v1/auth/login", {
    method: "POST",
    body: payload,
  });
}

/** POST /api/v1/auth/refresh. */
export function refresh(payload: RefreshRequest): Promise<TokenResponse> {
  return apiRequest<TokenResponse>("/api/v1/auth/refresh", {
    method: "POST",
    body: payload,
  });
}

/** GET /api/v1/auth/me (requires system:read). */
export function me(token: string): Promise<CurrentUserResponse> {
  return apiRequest<CurrentUserResponse>("/api/v1/auth/me", { token });
}
