import { AreaUnavailable } from "@/components/area-unavailable";

export default function PnlPage() {
  return (
    <AreaUnavailable
      area="P&L"
      description="P&L figures come from the Phase 13 P&L Engine; no P&L REST endpoint is exposed yet."
      expectedData={["Realized / unrealized", "Gross / costs / net", "Daily P&L", "Strategy P&L", "Account P&L"]}
    />
  );
}
