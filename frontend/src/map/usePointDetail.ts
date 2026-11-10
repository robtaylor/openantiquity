import { fetchGeoPoint, type GeoPoint } from "../api/geo.js";
import { useOptionalEndpointQuery } from "../api/useOptionalEndpointQuery.js";
import { useDebounced } from "../ui/useDebounced.js";

/** How long the pointer, or the map on a touch screen, must rest before the server is asked about the spot. */
export const POINT_REST_MS = 400;

/** A position to five decimal places, about a metre, which is as fine as the readout needs. */
function positionKey(position: { lng: number; lat: number } | null): string | null {
  return position === null ? null : `${position.lng.toFixed(5)},${position.lat.toFixed(5)}`;
}

export interface PointDetail {
  /** What the server says about the spot under the pointer, once it has rested there. Null until then. */
  detail: GeoPoint | null;
  /** True once the server has said it has no `/geo/point`. Nothing more is asked of it. */
  missing: boolean;
}

/**
 * The exact grid reference and ground height at `position`, from
 * `GET /geo/point`, asked for once the position has rested for
 * `POINT_REST_MS`. A pointer sweeping across the map asks nothing, and a
 * request for a spot the pointer has left is cancelled.
 *
 * The readout works without it, so any failure is quiet: the detail stays
 * null, and the next resting place is asked about afresh. A server without
 * the endpoint is not asked again for the life of the page.
 */
export function usePointDetail(position: { lng: number; lat: number } | null): PointDetail {
  const key = positionKey(position);
  // Nothing is asked until the position has rested, including where the map opens.
  const settled = useDebounced(key, POINT_REST_MS, null);

  const { query, missing } = useOptionalEndpointQuery({
    queryKey: ["geo", "point", settled],
    queryFn: ({ signal }) => {
      if (settled === null) throw new Error("usePointDetail ran with no position");
      const [lng, lat] = settled.split(",").map(Number) as [number, number];
      return fetchGeoPoint(lng, lat, signal);
    },
    enabled: settled !== null,
    staleTime: Number.POSITIVE_INFINITY,
    gcTime: 5 * 60_000,
    retry: false,
  });

  // An answer for where the pointer was is no answer for where it is.
  const current = key !== null && key === settled && !missing ? (query.data ?? null) : null;
  return { detail: current, missing };
}
