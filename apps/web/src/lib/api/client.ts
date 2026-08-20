import { API_BASE_URL } from "@/lib/env";
import { ApiError, parseApiError } from "./errors";

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  /** Optional bearer access token. */
  token?: string | null;
  body?: unknown;
  signal?: AbortSignal;
}

/**
 * Thin authenticated fetch wrapper over the backend REST API.
 *
 * - Always sends JSON, always parses the backend error envelope.
 * - Throws ApiError (with status/code/requestId) on any non-2xx response.
 * - Never logs tokens; never exposes raw response bodies on error.
 */
export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (options.token) {
    headers["Authorization"] = `Bearer ${options.token}`;
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: options.method ?? "GET",
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      signal: options.signal,
    });
  } catch (err) {
    // Network failure / timeout — no backend response to parse.
    throw new ApiError(0, "NETWORK_ERROR", "Unable to reach the trading API.", "unknown");
  }

  const text = await response.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = null;
    }
  }

  if (!response.ok) {
    throw parseApiError(response.status, body);
  }

  return body as T;
}
