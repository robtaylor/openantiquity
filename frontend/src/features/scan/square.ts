/**
 * Plain geometry for scanning a square: framing it on the map, the shade
 * over everything outside it, whether a point is in it, and the box the
 * coverage layer asks about.
 */

import { kmSquareAt } from "../../map/gridref.js";
import { centreForVisible, type MapCover, NO_COVER, visibleCentre } from "../../map/visibleArea.js";
import type { GeoJSONGeometry } from "../findings/types.js";
import { EMPTY_COLLECTION, type FeatureCollection } from "../records/geojson.js";
import { type CoverageCollection, MAX_COVERAGE_KM2, type Square } from "./api.js";

/** West, south, east, north in degrees. */
export type Box = readonly [number, number, number, number];
export type Ring = Array<[number, number]>;

export class ScanGeometryError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ScanGeometryError";
  }
}

/** How much of the uncovered map the square takes up, across its narrower side, once framed. */
export const SQUARE_FILL = 0.8;
/** The closest the map comes to frame a square, so a very large window doesn't go in further than the data. */
const MAX_FRAME_ZOOM = 17;

/**
 * Where to point a north-up camera so the square fills `SQUARE_FILL` of the
 * part of a `width` by `height` map that `cover` leaves uncovered, with its
 * middle in the middle of that part. MapLibre draws 512 px a tile, and
 * Mercator stretches latitude by 1 / cos(latitude).
 */
export function frameSquare(
  bbox: Box,
  width: number,
  height: number,
  cover: MapCover = NO_COVER,
): { lng: number; lat: number; zoom: number } {
  const [west, south, east, north] = bbox;
  if (!(west < east && south < north))
    throw new ScanGeometryError(`A square's box must run west to east and south to north`);
  const lat = (south + north) / 2;
  const stretch = 1 / Math.cos((lat * Math.PI) / 180);
  const across = ((east - west) / 360) * 512;
  const up = ((north - south) / 360) * 512 * stretch;
  const visibleWidth = Math.max(1, width - cover.left - cover.right);
  const visibleHeight = Math.max(1, height - cover.top - cover.bottom);
  const zoomToFit = (pixels: number, span: number) => Math.log2((pixels * SQUARE_FILL) / span);
  const zoom = Math.max(0, Math.min(MAX_FRAME_ZOOM, zoomToFit(visibleWidth, across), zoomToFit(visibleHeight, up)));
  return { ...centreForVisible((west + east) / 2, lat, zoom, cover), zoom };
}

/**
 * Where to point the camera so the ground in the middle of the uncovered map
 * stays in the middle when the cover changes from `before` to `after`, as
 * when the phone's sheet drops from half-way to peek for marking. Null when
 * nothing moved, or when the map is turned from north, which
 * `centreForVisible` doesn't handle.
 */
export function keepMiddle(
  camera: { lng: number; lat: number; zoom: number; bearing?: number },
  before: MapCover,
  after: MapCover,
): { lng: number; lat: number } | null {
  if ((camera.bearing ?? 0) !== 0) return null;
  if (
    before.left === after.left &&
    before.right === after.right &&
    before.top === after.top &&
    before.bottom === after.bottom
  )
    return null;
  const middle = visibleCentre(camera, before);
  return centreForVisible(middle.lng, middle.lat, camera.zoom, after);
}

/** The square's outer ring, as the server drew it. */
export function squareRing(geometry: GeoJSONGeometry): Ring {
  const coordinates: unknown = geometry.coordinates;
  const outer = geometry.type === "Polygon" && Array.isArray(coordinates) ? coordinates[0] : undefined;
  if (!Array.isArray(outer) || outer.length < 4) throw new ScanGeometryError("A square must be a polygon");
  return outer.map((point: unknown): [number, number] => {
    if (!Array.isArray(point) || typeof point[0] !== "number" || typeof point[1] !== "number") {
      throw new ScanGeometryError("A square's corner must be a pair of numbers");
    }
    return [point[0], point[1]];
  });
}

/** The world, as far north and south as the map goes, wound the other way round from a hole in it. */
const WORLD: Ring = [
  [-180, -85],
  [180, -85],
  [180, 85],
  [-180, 85],
  [-180, -85],
];

/** Shoelace sum: positive for a ring that runs anticlockwise. */
function signedArea(ring: Ring): number {
  let sum = 0;
  for (let i = 0; i + 1 < ring.length; i++) {
    const [x1, y1] = ring[i] as [number, number];
    const [x2, y2] = ring[i + 1] as [number, number];
    sum += x1 * y2 - x2 * y1;
  }
  return sum / 2;
}

/**
 * The square's outline, and the shade over everything outside it: the
 * world with the square cut out. A hole runs clockwise, against the outer
 * ring, as GeoJSON asks.
 */
export function squareFeatures(square: Square | null): { outline: FeatureCollection; shade: FeatureCollection } {
  if (!square) return { outline: EMPTY_COLLECTION, shade: EMPTY_COLLECTION };
  const ring = squareRing(square.geometry);
  const hole = signedArea(ring) > 0 ? [...ring].reverse() : ring;
  return {
    outline: {
      type: "FeatureCollection",
      features: [{ type: "Feature", geometry: { type: "Polygon", coordinates: [ring] }, properties: {} }],
    },
    shade: {
      type: "FeatureCollection",
      features: [{ type: "Feature", geometry: { type: "Polygon", coordinates: [WORLD, hole] }, properties: {} }],
    },
  };
}

/** True when the point lies in the one-kilometre square named `square`, such as "SU1069". */
export function inSquare(square: string, [lon, lat]: readonly [number, number]): boolean {
  return kmSquareAt(lon, lat)?.ref === square;
}

/** Roughly how many square kilometres a box in degrees covers, as the server reckons it. */
export function areaKm2([west, south, east, north]: Box): number {
  const middle = (((south + north) / 2) * Math.PI) / 180;
  return (east - west) * 111.32 * Math.cos(middle) * (north - south) * 110.57;
}

/** Coverage is asked for on a grid this many degrees across, so small moves reuse an answer. */
const COVERAGE_STEP = 0.02;

/**
 * The box to ask coverage about for a view: the view pushed out to the grid,
 * or null when that is more than the server answers for, which is about
 * zoom 10 on a desktop screen.
 */
export function coverageBox([west, south, east, north]: Box): Box | null {
  const down = (value: number) => Math.round(Math.floor(value / COVERAGE_STEP) * COVERAGE_STEP * 100) / 100;
  const up = (value: number) => Math.round(Math.ceil(value / COVERAGE_STEP) * COVERAGE_STEP * 100) / 100;
  const box: Box = [
    Math.max(-180, down(west)),
    Math.max(-85, down(south)),
    Math.min(180, up(east)),
    Math.min(85, up(north)),
  ];
  return areaKm2(box) <= MAX_COVERAGE_KM2 ? box : null;
}

/**
 * The coverage answer as features for the map: each scanned square's
 * outline, with its reference and how many people have scanned it.
 */
export function coverageFeatures(collection: CoverageCollection): FeatureCollection {
  return {
    type: "FeatureCollection",
    features: (collection.features ?? []).map((feature) => ({
      type: "Feature",
      id: feature.id,
      geometry: { type: "Polygon", coordinates: [squareRing(feature.geometry)] },
      properties: { square: feature.properties.square, scans: feature.properties.scans },
    })),
  };
}
