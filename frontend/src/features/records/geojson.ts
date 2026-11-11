/**
 * The few GeoJSON shapes the records feature builds for the map. MapLibre's
 * own declarations use the `geojson` package, which this project does not
 * depend on directly, so these are kept to what is drawn here.
 */

export type Position = [number, number];

export type Geometry =
  | { type: "Point"; coordinates: Position }
  | { type: "MultiPoint"; coordinates: Position[] }
  | { type: "LineString"; coordinates: Position[] }
  | { type: "MultiLineString"; coordinates: Position[][] }
  | { type: "Polygon"; coordinates: Position[][] }
  | { type: "MultiPolygon"; coordinates: Position[][][] };

export type Polygon = Extract<Geometry, { type: "Polygon" }>;

export interface Feature {
  type: "Feature";
  id?: string | number;
  geometry: Geometry;
  properties: Record<string, string | number | boolean | null>;
}

export interface FeatureCollection {
  type: "FeatureCollection";
  features: Feature[];
}

export const EMPTY_COLLECTION: FeatureCollection = Object.freeze({
  type: "FeatureCollection",
  features: [],
}) as FeatureCollection;
