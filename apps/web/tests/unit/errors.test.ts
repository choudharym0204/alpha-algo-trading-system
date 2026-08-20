import { describe, expect, it } from "vitest";
import { ApiError, parseApiError, isApiErrorBody } from "@/lib/api/errors";

describe("parseApiError", () => {
  it("parses the backend structured envelope", () => {
    const error = parseApiError(401, {
      error: {
        code: "AUTH_REQUIRED",
        message: "Authentication required.",
        request_id: "abc-123",
        details: {},
      },
    });
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(401);
    expect(error.code).toBe("AUTH_REQUIRED");
    expect(error.message).toBe("Authentication required.");
    expect(error.requestId).toBe("abc-123");
    expect(error.isUnauthorized).toBe(true);
  });

  it("falls back safely on a non-envelope body", () => {
    const error = parseApiError(502, "<html>Bad Gateway</html>");
    expect(error.code).toBe("UNEXPECTED_RESPONSE");
    expect(error.message).toBe("The server returned an unexpected response.");
    expect(error.requestId).toBe("unknown");
  });

  it("treats 403 as forbidden", () => {
    const error = parseApiError(403, {
      error: { code: "FORBIDDEN", message: "Required permission is missing.", request_id: "r1", details: {} },
    });
    expect(error.isForbidden).toBe(true);
  });
});

describe("isApiErrorBody", () => {
  it("rejects null, primitives, and malformed envelopes", () => {
    expect(isApiErrorBody(null)).toBe(false);
    expect(isApiErrorBody("text")).toBe(false);
    expect(isApiErrorBody({})).toBe(false);
    expect(isApiErrorBody({ error: { code: "X" } })).toBe(false);
  });

  it("accepts a well-formed envelope", () => {
    expect(isApiErrorBody({ error: { code: "X", message: "M", request_id: "R" } })).toBe(true);
  });
});
