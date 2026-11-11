import { squareWords } from "../../features/findings/square.js";
import type { CoverageCollection, Square } from "../../features/scan/api.js";
import { kmSquareAt } from "../../map/gridref.js";

/**
 * Squares for "Scan a square", as `GET /squares/next` returns them, drawn
 * from the frontend's own grid conversion so the reference, the outline and
 * the box agree. The default is the square holding the findings fixtures'
 * spot near Avebury, SU 10 69.
 */

export const SQUARE_SPOT: [number, number] = [-1.8542, 51.4286];

export function squareAt(lon: number, lat: number, scans = 0): Square {
  const found = kmSquareAt(lon, lat);
  if (!found) throw new Error(`No grid square at ${lon}, ${lat}`);
  const lngs = found.ring.map((point) => point[0]);
  const lats = found.ring.map((point) => point[1]);
  const round = (value: number) => Math.round(value * 1e6) / 1e6;
  const bbox: Square["bbox"] = [
    round(Math.min(...lngs)),
    round(Math.min(...lats)),
    round(Math.max(...lngs)),
    round(Math.max(...lats)),
  ];
  const corners = found.ring.slice(0, 4);
  const centre: Square["centre"] = [
    round(corners.reduce((sum, point) => sum + point[0], 0) / 4),
    round(corners.reduce((sum, point) => sum + point[1], 0) / 4),
  ];
  return {
    square: found.ref,
    grid_ref: squareWords(found.ref),
    centre,
    bbox,
    geometry: { type: "Polygon", coordinates: [found.ring.map(([x, y]) => [round(x), round(y)])] },
    scans,
  };
}

/** The square `steps` kilometres east of the default one. */
export function squareEastOf(steps: number, scans = 0): Square {
  return squareAt(SQUARE_SPOT[0] + steps * 0.0145, SQUARE_SPOT[1], scans);
}

/** `GET /squares/coverage` naming these squares with these counts. */
export function coverageOf(entries: Array<{ square: Square; scans: number; marked?: number }>): CoverageCollection {
  return {
    type: "FeatureCollection",
    features: entries.map(({ square, scans, marked = 0 }) => ({
      type: "Feature",
      id: square.square,
      geometry: square.geometry,
      properties: { square: square.square, scans, marked },
    })),
  };
}
