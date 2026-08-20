import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { TradingModeBadge } from "@/components/shell/trading-mode-badge";

describe("TradingModeBadge (LIVE-safety)", () => {
  it("shows PAPER for a disabled backend", () => {
    render(<TradingModeBadge liveTrading="disabled" />);
    expect(screen.getByText("PAPER")).toBeInTheDocument();
  });

  it("never renders LIVE when the backend is disabled", () => {
    render(<TradingModeBadge liveTrading="disabled" />);
    expect(screen.queryByText("LIVE")).not.toBeInTheDocument();
  });

  it("renders LIVE only for the explicit 'enabled' signal", () => {
    render(<TradingModeBadge liveTrading="enabled" />);
    expect(screen.getByText("LIVE")).toBeInTheDocument();
  });

  it("renders MODE UNKNOWN for an unknown signal (not LIVE)", () => {
    render(<TradingModeBadge liveTrading="bogus" />);
    expect(screen.getByText("MODE UNKNOWN")).toBeInTheDocument();
    expect(screen.queryByText("LIVE")).not.toBeInTheDocument();
  });
});
