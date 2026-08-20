import { AreaUnavailable } from "@/components/area-unavailable";

export default function ChartsPage() {
  return (
    <AreaUnavailable
      area="Charts"
      description="Candlestick/volume charts need historical OHLC from the backend; no charting data endpoint exists yet."
      expectedData={["Candlesticks", "Volume", "Timeframe selection", "Crosshair / zoom / pan", "Data freshness"]}
    />
  );
}
