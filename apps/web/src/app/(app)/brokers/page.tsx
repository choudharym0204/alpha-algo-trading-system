import { AreaUnavailable } from "@/components/area-unavailable";

export default function BrokersPage() {
  return (
    <AreaUnavailable
      area="Brokers"
      description="Broker adapter status comes from the Phase 10 adapters; no broker REST endpoint is exposed yet. Credentials never reach the browser."
      expectedData={["Broker name", "Connection / session state", "Health", "Supported capabilities", "Rate-limit state"]}
    />
  );
}
