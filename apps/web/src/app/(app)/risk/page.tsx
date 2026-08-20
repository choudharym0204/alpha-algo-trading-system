import { AreaUnavailable } from "@/components/area-unavailable";

export default function RiskPage() {
  return (
    <AreaUnavailable
      area="Risk"
      description="Risk state comes from the Phase 6 Risk Engine; no risk REST endpoint is exposed yet. The global trading halt is reflected on the Dashboard via the backend safety flags."
      expectedData={["Risk status", "Approvals / rejections", "Global halt", "Active limits", "Circuit breaker state"]}
    />
  );
}
