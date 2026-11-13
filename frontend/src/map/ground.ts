/**
 * Distances along the ground, for readouts, limits and choosing between
 * shapes. A sphere of the mean Earth radius, as the server measures a
 * path's length, so the drawing tool's length matches the server's
 * (`docs/architecture/curve-vectors.json`). Nothing here knows about React
 * or the map library.
 */

/** The mean radius of the Earth, in metres. */
export const EARTH_RADIUS_M = 6_371_008.8;

function radians(degrees: number): number {
  return (degrees * Math.PI) / 180;
}

/** The great-circle distance between two places, longitude then latitude in degrees, in metres. */
export function groundDistanceM(
  [lon1, lat1]: readonly [number, number],
  [lon2, lat2]: readonly [number, number],
): number {
  const dLat = radians(lat2 - lat1);
  const dLon = radians(lon2 - lon1);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(radians(lat1)) * Math.cos(radians(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(h)));
}

/** The length of a line through the places in order, in metres. Nothing for fewer than two. */
export function lineLengthM(line: ReadonlyArray<readonly [number, number]>): number {
  let total = 0;
  for (let i = 1; i < line.length; i++) {
    const a = line[i - 1];
    const b = line[i];
    if (a && b) total += groundDistanceM(a, b);
  }
  return total;
}
