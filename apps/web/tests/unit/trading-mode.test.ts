import { describe, expect, it } from "vitest";
import { resolveTradingMode, isLiveTradingEnabled } from "@/lib/trading-mode";

describe("resolveTradingMode (fail-closed)", () => {
  it("maps 'disabled' to PAPER, never LIVE", () => {
    expect(resolveTradingMode("disabled")).toBe("PAPER");
  });

  it("maps 'enabled' to LIVE", () => {
    expect(resolveTradingMode("enabled")).toBe("LIVE");
  });

  it("maps unknown/missing values to UNKNOWN, never LIVE", () => {
    expect(resolveTradingMode("bogus")).toBe("UNKNOWN");
    expect(resolveTradingMode(null)).toBe("UNKNOWN");
    expect(resolveTradingMode(undefined)).toBe("UNKNOWN");
  });

  it("never enables live for anything but the exact 'enabled' string", () => {
    expect(isLiveTradingEnabled("disabled")).toBe(false);
    expect(isLiveTradingEnabled("DISABLED")).toBe(false);
    expect(isLiveTradingEnabled("1")).toBe(false);
    expect(isLiveTradingEnabled("enabled")).toBe(true);
  });
});
