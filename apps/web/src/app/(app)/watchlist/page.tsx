import { AreaUnavailable } from "@/components/area-unavailable";

export default function WatchlistPage() {
  return (
    <AreaUnavailable
      area="Watchlist"
      description="A persistent watchlist requires a backend watchlist store and quote-feed, neither of which is exposed yet."
      expectedData={["Add / remove instrument", "Reorder", "Search", "Quote updates", "Stale-data indication"]}
    />
  );
}
