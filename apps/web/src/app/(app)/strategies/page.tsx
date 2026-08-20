import { AreaUnavailable } from "@/components/area-unavailable";

export default function StrategiesPage() {
  return (
    <AreaUnavailable
      area="Strategies"
      description="Strategy run status and signals come from the Phase 4/5 runtime; no strategy REST/WS endpoint is exposed yet."
      expectedData={["Strategy name / version", "Run status", "Trading mode", "Generated signals", "Strategy health"]}
    />
  );
}
