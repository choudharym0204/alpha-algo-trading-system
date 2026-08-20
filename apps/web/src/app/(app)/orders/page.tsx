import { AreaUnavailable } from "@/components/area-unavailable";

export default function OrdersPage() {
  return (
    <AreaUnavailable
      area="Orders"
      description="Order listing and order entry require OMS/Execution REST endpoints, which are not exposed yet. No order can be submitted from the browser until the backend routes exist."
      expectedData={["Open orders", "Order history", "Status / filled / remaining", "Average fill price", "Rejection reason"]}
    />
  );
}
