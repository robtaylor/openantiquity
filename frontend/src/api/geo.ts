import { apiFetch } from "./client.js";
import { isFiniteNumber, isRecord } from "./guards.js";

/**
 * `GET /geo/point?lon=&lat=`: what the server knows about one spot. The
 * contract names its contents (grid reference, nation, elevation) but not
 * its fields, and the endpoint is not built yet. This reads the shape below,
 * which follows the names used elsewhere in the API:
 *
 *     {"grid_ref": "SU 10235 69874", "nation": "england", "elevation": 162.4}
 *
 * `elevation` is the ground height in metres, or null where there is no
 * elevation data. Fields the server leaves out come back as null.
 */
export interface GeoPoint {
  grid_ref: string | null;
  nation: string | null;
  elevation: number | null;
}

export class GeoPointError extends Error {
  constructor(message: string) {
    super(`Unexpected /geo/point answer: ${message}`);
    this.name = "GeoPointError";
  }
}

export function parseGeoPoint(value: unknown): GeoPoint {
  if (!isRecord(value)) throw new GeoPointError("not an object");
  const { grid_ref: gridRef, nation, elevation } = value;
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
  };
}

export async function fetchGeoPoint(lng: number, lat: number, signal?: AbortSignal): Promise<GeoPoint> {
  const body = await apiFetch<unknown>("/geo/point", { query: { lon: lng, lat }, signal });
  return parseGeoPoint(body);
}
