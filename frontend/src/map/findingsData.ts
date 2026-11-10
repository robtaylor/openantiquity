import type { FindingCollection, FindingFeature } from "../features/findings/types.js";
import { kmSquareAt } from "./gridref.js";

/**
 * What the findings source on the map holds, built from a findings response.
 *
 * A finding whose position is exact stays a point. A finding with `obscured`
 * set is never drawn as a point: it becomes the outline of its one-kilometre
 * grid square, on the British or Irish grid as appropriate, for the dashed
 * square layers. Any sensitivity level can arrive obscured, depending on who
 * is looking, so only `obscured` decides.
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
}

export type FindingsMapFeature =
  | { type: "Feature"; geometry: { type: "Point"; coordinates: [number, number] }; properties: PointProperties }
  | {
      type: "Feature";
      geometry: { type: "Polygon"; coordinates: [Array<[number, number]>] };
      properties: SquareProperties;
    };

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
      continue;
    }
    squares.set(key, {
      type: "Feature",
      geometry: { type: "Polygon", coordinates: [square.ring] },
      properties: { square: square.ref, tier, state, count: 1 },
    });
  }
  return [...squares.entries()].sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)).map(([, feature]) => feature);
}

export function findingsMapData(collection: FindingCollection): FindingsMapData {
  const points: FindingsMapFeature[] = [];
  const obscured: FindingFeature[] = [];
  for (const feature of collection.features) {
    if (feature.properties.obscured) {
      obscured.push(feature);
      continue;
    }
    const { public_id: publicId, tier, state } = feature.properties;
    points.push({
      type: "Feature",
      geometry: { type: "Point", coordinates: feature.geometry.coordinates },
      properties: { public_id: publicId, tier, state },
    });
  }
  return { type: "FeatureCollection", features: [...squaresFrom(obscured), ...points] };
}
