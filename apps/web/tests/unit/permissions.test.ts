import { describe, expect, it } from "vitest";
import { hasPermission, hasAnyPermission, PERMISSIONS } from "@/lib/auth/permissions";

describe("hasPermission", () => {
  it("grants when the permission is present", () => {
    expect(hasPermission(["system:read", "trading:view"], PERMISSIONS.SYSTEM_READ)).toBe(true);
  });

  it("denies when the permission is absent", () => {
    expect(hasPermission(["trading:view"], PERMISSIONS.LIVE_TRADE)).toBe(false);
  });

  it("denies on null/undefined/empty permission lists", () => {
    expect(hasPermission(null, PERMISSIONS.SYSTEM_READ)).toBe(false);
    expect(hasPermission(undefined, PERMISSIONS.SYSTEM_READ)).toBe(false);
    expect(hasPermission([], PERMISSIONS.SYSTEM_READ)).toBe(false);
  });
});

describe("hasAnyPermission", () => {
  it("returns true if any required permission is held", () => {
    expect(hasAnyPermission(["trading:view"], [PERMISSIONS.TRADING_VIEW, PERMISSIONS.LIVE_TRADE])).toBe(true);
  });

  it("returns false if none are held", () => {
    expect(hasAnyPermission(["system:read"], [PERMISSIONS.TRADING_VIEW, PERMISSIONS.LIVE_TRADE])).toBe(false);
  });
});
