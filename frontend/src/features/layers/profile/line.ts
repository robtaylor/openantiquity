import { centreForVisible, type MapCover, NO_COVER } from "../../../map/visibleArea.js";
/**
 * The line a height profile is drawn along: how it is written in the
 * address, how long it is, and which sample is nearest the pointer.
 */

/** Longitude, then latitude, in degrees. */
export type LngLat = [number, number];

export const PROFILE_PATH = "/profile";
export const LINE_PARAM = "line";

/**
 * The most points a line may have. The backend refuses more
 * (`MAX_PROFILE_VERTICES` in terrain/service.py); the schema does not carry
 * the limit, so it is repeated here.
 */
export const MAX_LINE_POINTS = 200;

/**
 * The most samples one profile may ask for (`MAX_PROFILE_SAMPLES`). The
 * backend reads its finest, 1 m, grid only when samples are at most a metre
 * apart, so a line asks for one a metre up to this.
 */
export const MAX_SAMPLES = 1000;

const EARTH_RADIUS_M = 6371008.8;

/** Five decimal places, about a metre. */
function fixed(value: number): string {
  return Number(value.toFixed(5)).toString();
}

/** The address of the profile panel with this line in it, to share or come back to. */
export function profilePath(points: readonly LngLat[]): string {
  if (points.length === 0) return PROFILE_PATH;
  return `${PROFILE_PATH}?${LINE_PARAM}=${points.map(([lng, lat]) => `${fixed(lng)},${fixed(lat)}`).join(",")}`;
}

/**
 * The points written in the address, as `lng,lat,lng,lat,...`. Anything that
 * isn't a run of valid pairs gives an empty line, so a damaged link opens an
 * empty profile rather than a wrong one.
 */
export function parseLine(value: string | null): LngLat[] {
  if (value === null || value.trim() === "") return [];
  const numbers = value.split(",").map((part) => (part.trim() === "" ? Number.NaN : Number(part)));
  if (numbers.length % 2 !== 0 || numbers.some((n) => !Number.isFinite(n))) return [];
  const points: LngLat[] = [];
  for (let i = 0; i < numbers.length; i += 2) {
    const lng = numbers[i] as number;
    const lat = numbers[i + 1] as number;
    if (Math.abs(lng) > 180 || Math.abs(lat) > 90) return [];
    points.push([lng, lat]);
  }
  return points.slice(0, MAX_LINE_POINTS);
}

/** Great-circle distance in metres. Near enough to the backend's grid distance for choosing a sample count. */
export function distanceM([lng1, lat1]: LngLat, [lng2, lat2]: LngLat): number {
  const rad = Math.PI / 180;
  const dLat = (lat2 - lat1) * rad;
  const dLng = (lng2 - lng1) * rad;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dLng / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(a)));
}

export function lineLengthM(points: readonly LngLat[]): number {
  let total = 0;
  for (let i = 1; i < points.length; i++) total += distanceM(points[i - 1] as LngLat, points[i] as LngLat);
  return total;
}

/** How many samples to ask for: about one a metre, so short lines are read from the 1 m grid. */
export function sampleCount(lengthM: number): number {
  if (!Number.isFinite(lengthM) || lengthM <= 0) return 2;
  return Math.min(MAX_SAMPLES, Math.max(2, Math.ceil(lengthM) + 1));
}

/**
 * The index of the screen point nearest `pointer`, or null when none is
 * within `reach` pixels. Used to find the sample under the pointer on the map.
 */
export function nearestIndex(
  points: ReadonlyArray<{ x: number; y: number }>,
  pointer: { x: number; y: number },
  reach: number,
): number | null {
  let best: number | null = null;
  let bestDistance = reach * reach;
  points.forEach((point, index) => {
    const distance = (point.x - pointer.x) ** 2 + (point.y - pointer.y) ** 2;
    if (distance <= bestDistance) {
      bestDistance = distance;
      best = index;
    }
  });
  return best;
}

/**
 * Where to point the camera so the whole line is in view, using about half the
 * width and height of the part of a `width` by `height` map that `cover`
 * leaves uncovered: a centre that puts the line's middle in the middle of that
 * part, and a zoom no closer than `maxZoom`. Mercator stretches latitude by
 * 1 / cos(latitude).
 */
export function framingFor(
  points: readonly LngLat[],
  width: number,
  height: number,
  cover: MapCover = NO_COVER,
  maxZoom = 17,
): { lng: number; lat: number; zoom: number } | null {
  if (points.length === 0) return null;
  const lngs = points.map((point) => point[0]);
  const lats = points.map((point) => point[1]);
  const west = Math.min(...lngs);
  const east = Math.max(...lngs);
  const south = Math.min(...lats);
  const north = Math.max(...lats);
  const lat = (south + north) / 2;
  const stretch = 1 / Math.cos((lat * Math.PI) / 180);
  // 512 px a tile, as MapLibre counts zoom.
  const across = ((east - west) / 360) * 512;
  const up = ((north - south) / 360) * 512 * stretch;
  const zoomToFit = (pixels: number, span: number) =>
    span > 0 ? Math.log2((Math.max(1, pixels) * 0.5) / span) : maxZoom;
  const visibleWidth = width - cover.left - cover.right;
  const visibleHeight = height - cover.top - cover.bottom;
  const zoom = Math.max(0, Math.min(maxZoom, zoomToFit(visibleWidth, across), zoomToFit(visibleHeight, up)));
  return { ...centreForVisible((west + east) / 2, lat, zoom, cover), zoom };
}

/** A distance for people: metres to a kilometre, then kilometres to two places. */
export function distanceText(metres: number): string {
  if (metres < 1000) return `${Math.round(metres)} m`;
  return `${(metres / 1000).toFixed(2)} km`;
}
