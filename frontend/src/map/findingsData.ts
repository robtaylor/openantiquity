import type { FindingCollection, FindingFeature, FindingShape } from "../features/findings/types.js";
import { kmSquareAt } from "./gridref.js";

/**
 * What the findings source on the map holds, built from a findings response.
 *
 * A finding whose position is exact stays a point. A finding with `obscured`
 * set is never drawn as a point: it becomes the outline of its one-kilometre
 * grid square, on the British or Irish grid as appropriate, for the dashed
 * square layers. Any sensitivity level can arrive obscured, depending on who
 * is looking, so only `obscured` decides.
 *
 * An exact finding with a line or an area keeps its point, the anchor
 * marker that names its tier and can be tapped, and gains a feature of its
 * shape, marked `shape: "line"` or `"area"` with its `size` for picking
 * between overlapping ones. An obscured finding is its square and nothing
 * else, whatever came with it.
 */

export interface PointProperties {
  public_id: string;
  tier: string;
  state: string;
}

export interface SquareProperties {
  square: string;
  tier: string;
  state: string;
  /** How many findings share the square in this state. */
  count: number;
  /**
   * Their public ids, separated by spaces, so a click on the square can
   * open them. Text, because MapLibre hands back nested values as JSON.
   */
  public_ids: string;
}

export interface ShapeProperties {
  public_id: string;
  tier: string;
  state: string;
  shape: "line" | "area";
  /**
   * How big it is, to tell the smaller of two alike: a line's length, and an
   * area's extent, the area of the box round it, in metres and square metres.
   */
  size: number;
}

export type FindingsMapFeature =
  | { type: "Feature"; geometry: { type: "Point"; coordinates: [number, number] }; properties: PointProperties }
  | {
      type: "Feature";
      geometry: { type: "Polygon"; coordinates: [Array<[number, number]>] };
      properties: SquareProperties;
    }
  | { type: "Feature"; geometry: FindingShape; properties: ShapeProperties };

export interface FindingsMapData {
  type: "FeatureCollection";
  features: FindingsMapFeature[];
}

/**
 * One square per grid square and state. Several obscured findings can share
 * a square, so squares are merged, keeping the tier of the first finding and
 * a count. A finding listed twice is counted once.
 */
function squaresFrom(features: readonly FindingFeature[]): FindingsMapFeature[] {
  const squares = new Map<string, FindingsMapFeature & { properties: SquareProperties }>();
  const counted = new Set<string>();
  for (const feature of features) {
    const [lon, lat] = feature.geometry.coordinates;
    const square = kmSquareAt(lon, lat);
    if (!square) continue;
    const { state, tier, public_id: publicId } = feature.properties;
    const key = `${square.ref}|${state}`;
    if (counted.has(`${key}|${publicId}`)) continue;
    counted.add(`${key}|${publicId}`);
    const existing = squares.get(key);
    if (existing) {
      existing.properties.count += 1;
      existing.properties.public_ids += ` ${publicId}`;
      continue;
    }
    squares.set(key, {
      type: "Feature",
      geometry: { type: "Polygon", coordinates: [square.ring] },
      properties: { square: square.ref, tier, state, count: 1, public_ids: publicId },
    });
  }
  return [...squares.entries()].sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)).map(([, feature]) => feature);
}

const EARTH_RADIUS_M = 6_371_000;

function groundDistanceM([lon1, lat1]: [number, number], [lon2, lat2]: [number, number]): number {
  const rad = Math.PI / 180;
  const dLat = (lat2 - lat1) * rad;
  const dLon = (lon2 - lon1) * rad;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(h)));
}

function lineLengthM(line: readonly [number, number][]): number {
  let total = 0;
  for (let i = 1; i < line.length; i++) {
    const a = line[i - 1];
    const b = line[i];
    if (a && b) total += groundDistanceM(a, b);
  }
  return total;
}

/** The area of the box round every point, in square metres. */
function extentM2(points: readonly [number, number][]): number {
  if (points.length === 0) return 0;
  const lons = points.map(([lon]) => lon);
  const lats = points.map(([, lat]) => lat);
  const [west, east, south, north] = [Math.min(...lons), Math.max(...lons), Math.min(...lats), Math.max(...lats)];
  const middle = (south + north) / 2;
  return groundDistanceM([west, middle], [east, middle]) * groundDistanceM([west, south], [west, north]);
}

function shapeProperties(feature: FindingFeature, shape: FindingShape): ShapeProperties {
  const { public_id: publicId, tier, state } = feature.properties;
  switch (shape.type) {
    case "LineString":
      return { public_id: publicId, tier, state, shape: "line", size: lineLengthM(shape.coordinates) };
    case "MultiLineString":
      return {
        public_id: publicId,
        tier,
        state,
        shape: "line",
        size: shape.coordinates.reduce((sum, part) => sum + lineLengthM(part), 0),
      };
    case "Polygon":
      return { public_id: publicId, tier, state, shape: "area", size: extentM2(shape.coordinates.flat()) };
    case "MultiPolygon":
      return { public_id: publicId, tier, state, shape: "area", size: extentM2(shape.coordinates.flat(2)) };
  }
}

export function findingsMapData(collection: FindingCollection): FindingsMapData {
  const shapes: FindingsMapFeature[] = [];
  const points: FindingsMapFeature[] = [];
  const obscured: FindingFeature[] = [];
  for (const feature of collection.features) {
    if (feature.properties.obscured) {
      obscured.push(feature);
      continue;
    }
    const { public_id: publicId, tier, state, shape } = feature.properties;
    if (shape) shapes.push({ type: "Feature", geometry: shape, properties: shapeProperties(feature, shape) });
    points.push({
      type: "Feature",
      geometry: { type: "Point", coordinates: feature.geometry.coordinates },
      properties: { public_id: publicId, tier, state },
    });
  }
  return { type: "FeatureCollection", features: [...shapes, ...squaresFrom(obscured), ...points] };
}
