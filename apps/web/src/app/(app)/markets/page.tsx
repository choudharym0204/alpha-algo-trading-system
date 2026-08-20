import { AreaUnavailable } from "@/components/area-unavailable";

export default function MarketsPage() {
  return (
    <AreaUnavailable
      area="Markets"
      description="Market-data (LTP, bid/ask, volume, OHLC) is served by the backend's Phase 3 market-data provider, which has no authenticated REST/WS endpoint yet."
      expectedData={["LTP / quote", "Bid / ask", "Volume", "OHLC", "Market status"]}
    />
  );
}
