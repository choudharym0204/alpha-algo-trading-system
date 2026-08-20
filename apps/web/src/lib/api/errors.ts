import type { ApiErrorBody } from "./types";

/** A normalized backend error, safe to render (no raw stack traces). */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string;
  readonly details: Record<string, unknown>;

  constructor(status: number, code: string, message: string, requestId: string, details: Record<string, unknown> = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.details = details;
  }

  get isUnauthorized(): boolean {
    return this.status === 401;
  }

  get isForbidden(): boolean {
    return this.status === 403;
  }
}

/**
 * Parse the backend's structured error envelope into an ApiError.
 *
 * The backend always returns `{ error: { code, message, request_id, details } }`
 * on failure (see apps/api/.../errors.py). If the body does not match that
 * shape (proxy error, gateway, etc.), we fall back to a generic INTERNAL-style
 * error and never trust or echo an arbitrary body.
 */
export function parseApiError(status: number, body: unknown): ApiError {
  if (isApiErrorBody(body)) {
    const envelope = body.error;
    return new ApiError(
      status,
      envelope.code,
      envelope.message,
      envelope.request_id,
      typeof envelope.details === "object" && envelope.details !== null
        ? (envelope.details as Record<string, unknown>)
        : {},
    );
  }
  return new ApiError(
    status,
    "UNEXPECTED_RESPONSE",
    "The server returned an unexpected response.",
    "unknown",
  );
}

export function isApiErrorBody(body: unknown): body is ApiErrorBody {
  if (typeof body !== "object" || body === null) return false;
  const error = (body as { error?: unknown }).error;
  if (typeof error !== "object" || error === null) return false;
  const e = error as { code?: unknown; message?: unknown; request_id?: unknown };
  return (
    typeof e.code === "string" &&
    typeof e.message === "string" &&
    typeof e.request_id === "string"
  );
}
