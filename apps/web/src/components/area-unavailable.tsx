import { DataUnavailable } from "@/components/data-unavailable";

/**
 * Thin wrapper for terminal areas whose backend endpoint is not yet exposed.
 * Keeps each route a one-liner while rendering an honest Unavailable state.
 */
export function AreaUnavailable({
  area,
  description,
  expectedData,
}: {
  area: string;
  description: string;
  expectedData: readonly string[];
}) {
  return <DataUnavailable area={area} description={description} expectedData={expectedData} />;
}
