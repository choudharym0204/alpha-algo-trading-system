import { AreaUnavailable } from "@/components/area-unavailable";

export default function ReconciliationsPage() {
  return (
    <AreaUnavailable
      area="Reconciliations"
      description="Reconciliation state comes from the Phase 14 engine; no reconciliation REST endpoint is exposed yet. Corrective actions are backend-only."
      expectedData={["Latest run / status", "Matched / mismatched", "Critical / open discrepancies", "Severity", "Evidence summary"]}
    />
  );
}
