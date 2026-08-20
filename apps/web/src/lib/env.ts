/**
 * Environment access (public-only).
 *
 * Every environment read is centralized here. Only NEXT_PUBLIC_* values are
 * readable from the browser; nothing here can ever surface a secret, and no
 * component reads process.env directly.
 */

function read(name: string, fallback: string): string {
  const value = process.env[name];
  return value && value.trim() ? value.trim().replace(/\/+$/, "") : fallback;
}

export const API_BASE_URL = read(
  "NEXT_PUBLIC_API_BASE_URL",
  "http://localhost:8000",
);

export const WS_URL = read("NEXT_PUBLIC_WS_URL", "ws://localhost:8000");

export const WS_PATH = "/api/v1/ws";
