import { AreaUnavailable } from "@/components/area-unavailable";

export default function AlertsPage() {
  return (
    <AreaUnavailable
      area="Alerts"
      description="Notification/alert history is backend-driven; no alert REST/WS endpoint is exposed yet."
      expectedData={["Order rejection / fill", "Risk rejection", "Broker disconnect", "Reconciliation discrepancy", "System / strategy failure"]}
    />
  );
}
