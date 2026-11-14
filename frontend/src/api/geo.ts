import { apiFetch, ENDPOINT_MISSING_STATUSES } from "./client.js";
import { isFiniteNumber, isRecord } from "./guards.js";

/**
 * `GET /geo/point?lon=&lat=`: what the server knows about one spot, read
 * from the parts the frontend uses:
 *
 *     {"grid_ref": "SU 10235 69874", "nation": "england", "elevation": 162.4,
 *      "place": {"name": "Avebury", "kind": "village", "distance_m": 640}}
 *
 * `elevation` is the ground height in metres, or null where there is no
 * elevation data. `place` is the nearest settlement within 10 km, or null.
 * Fields the server leaves out come back as null.
 */
export interface GeoPoint {
  grid_ref: string | null;
  nation: string | null;
  elevation: number | null;
  place: NearbyPlace | null;
}

export interface NearbyPlace {
  name: string;
  kind: string;
  distance_m: number;
}

function parsePlace(value: unknown): NearbyPlace | null {
  if (!isRecord(value) || typeof value.name !== "string" || value.name === "") return null;
  if (!isFiniteNumber(value.distance_m)) return null;
  return { name: value.name, kind: typeof value.kind === "string" ? value.kind : "", distance_m: value.distance_m };
}

export class GeoPointError extends Error {
  constructor(message: string) {
    super(`Unexpected /geo/point answer: ${message}`);
    this.name = "GeoPointError";
  }
}

export function parseGeoPoint(value: unknown): GeoPoint {
  if (!isRecord(value)) throw new GeoPointError("not an object");
  const { grid_ref: gridRef, nation, elevation, place } = value;
  if (gridRef !== undefined && gridRef !== null && typeof gridRef !== "string") {
    throw new GeoPointError('"grid_ref" is not text');
  }
  if (elevation !== undefined && elevation !== null && !isFiniteNumber(elevation)) {
    throw new GeoPointError('"elevation" is not a number');
  }
  return {
    grid_ref: typeof gridRef === "string" && gridRef !== "" ? gridRef : null,
    nation: typeof nation === "string" ? nation : null,
    elevation: typeof elevation === "number" ? elevation : null,
    place: parsePlace(place),
  };
}

export async function fetchGeoPoint(lng: number, lat: number, signal?: AbortSignal): Promise<GeoPoint> {
  const body = await apiFetch<unknown>("/geo/point", {
    query: { lon: lng, lat },
    signal,
    expected: ENDPOINT_MISSING_STATUSES,
  });
  return parseGeoPoint(body);
}
