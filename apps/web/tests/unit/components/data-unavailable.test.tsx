import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { DataUnavailable } from "@/components/data-unavailable";

describe("DataUnavailable (honest boundary)", () => {
  it("marks the area Unavailable and lists expected data without fabricating values", () => {
    render(
      <DataUnavailable
        area="Positions"
        description="No position endpoint yet."
        expectedData={["Instrument", "Quantity", "Unrealized P&L"]}
      />,
    );
    expect(screen.getByText("Positions")).toBeInTheDocument();
    expect(screen.getByText("Unavailable")).toBeInTheDocument();
    expect(screen.getByText("Instrument")).toBeInTheDocument();
    expect(screen.getByText("Quantity")).toBeInTheDocument();
    expect(screen.getByText("Unrealized P&L")).toBeInTheDocument();
  });

  it("does not render a zero financial value", () => {
    render(
      <DataUnavailable area="P&L" description="No P&L endpoint yet." expectedData={["Net P&L"]} />,
    );
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });
});
