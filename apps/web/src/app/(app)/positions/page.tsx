import { AreaUnavailable } from "@/components/area-unavailable";

export default function PositionsPage() {
  return (
    <AreaUnavailable
      area="Positions"
      description="Position data comes from the Phase 11 Position Engine; no position REST endpoint is exposed yet."
      expectedData={["Instrument", "Quantity / side", "Average entry", "Reference price", "Unrealized P&L"]}
    />
  );
}
