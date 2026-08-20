import { describe, expect, it } from "vitest";
import {
  setSession,
  getSession,
  clearSession,
  isAccessTokenUsable,
} from "@/lib/auth/session-store";

describe("session store (in-memory)", () => {
  it("starts empty", () => {
    expect(getSession()).toBeNull();
  });

  it("stores and retrieves a session", () => {
    setSession({ accessToken: "a", refreshToken: "r", accessExpiresAt: Date.now() + 60000 });
    expect(getSession()?.accessToken).toBe("a");
  });

  it("clears the session", () => {
    setSession({ accessToken: "a", refreshToken: "r", accessExpiresAt: Date.now() + 60000 });
    clearSession();
    expect(getSession()).toBeNull();
  });

  it("treats a token as usable before expiry (5s skew)", () => {
    const session = { accessToken: "a", refreshToken: "r", accessExpiresAt: Date.now() + 10000 };
    expect(isAccessTokenUsable(session, Date.now())).toBe(true);
  });

  it("treats a token as unusable within the skew window", () => {
    const session = { accessToken: "a", refreshToken: "r", accessExpiresAt: Date.now() + 2000 };
    expect(isAccessTokenUsable(session, Date.now())).toBe(false);
  });
});
