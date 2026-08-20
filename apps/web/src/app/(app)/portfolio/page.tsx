import { AreaUnavailable } from "@/components/area-unavailable";

export default function PortfolioPage() {
  return (
    <AreaUnavailable
      area="Portfolio"
      description="Portfolio aggregates come from the Phase 12 Portfolio Engine; no portfolio REST endpoint is exposed yet."
      expectedData={["Portfolio value", "Cash / available funds", "Gross / net exposure", "Position count", "Degraded-state flag"]}
    />
  );
}
