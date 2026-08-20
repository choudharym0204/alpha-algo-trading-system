import { describe, expect, it } from "vitest";
import { normalizeWsEvent } from "@/lib/ws/client";

describe("normalizeWsEvent (typed event model)", () => {
  it("accepts a valid HEALTH_UPDATE", () => {
    const event = normalizeWsEvent(
      JSON.stringify({ type: "HEALTH_UPDATE", payload: { service: "alpha-algo", status: "ok", live_trading: "disabled" } }),
    );
    expect(event).toEqual({
      type: "HEALTH_UPDATE",
      payload: { service: "alpha-algo", status: "ok", live_trading: "disabled" },
    });
  });

  it("rejects unknown event types", () => {
    expect(normalizeWsEvent(JSON.stringify({ type: "ORDER_FILL", payload: {} }))).toBeNull();
  });

  it("rejects malformed payloads", () => {
    expect(normalizeWsEvent(JSON.stringify({ type: "HEALTH_UPDATE", payload: { status: "ok" } }))).toBeNull();
    expect(normalizeWsEvent(JSON.stringify({ type: "HEALTH_UPDATE", payload: { service: 1, status: "ok", live_trading: "disabled" } }))).toBeNull();
  });

  it("rejects non-JSON / non-string input", () => {
    expect(normalizeWsEvent("not json")).toBeNull();
    expect(normalizeWsEvent(42)).toBeNull();
    expect(normalizeWsEvent(null)).toBeNull();
  });
});
