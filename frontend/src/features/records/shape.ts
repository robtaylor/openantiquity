import { create } from "zustand";
import { isFiniteNumber, isRecord } from "../../api/guards.js";
import { kmSquareAt } from "../../map/gridref.js";
import type { RecordOut } from "./api.js";

import type { Feature, FeatureCollection, Geometry, Polygon } from "./geojson.js";

/**
 * How a record is drawn when its page is open. A record the source published
 * only to a square (a Portable Antiquities find to a one-kilometre square,
 * say) is drawn as that square, dashed, and never as a point, because a
 * point would claim an exactness the record doesn't have.
 */

/** From this coarseness up, a position is a square and not a spot. */
export const SQUARE_PRECISION_M = 1000;

export interface RecordShape {
  collection: FeatureCollection;
  /** True when the record is drawn as the square its position is known to. */
  imprecise: boolean;
  /** The one-kilometre square's grid reference, such as "SU1069", when it is one. */
  square: string | null;
}

const METRES_PER_DEGREE = 111_320;

/** A square `side` metres across centred on a point, near enough for drawing. */
function squareAround(lon: number, lat: number, side: number): Polygon {
  const halfLat = side / 2 / METRES_PER_DEGREE;
  const halfLon = halfLat / Math.max(0.2, Math.cos((lat * Math.PI) / 180));
  return {
    type: "Polygon",
    coordinates: [
      [
        [lon - halfLon, lat - halfLat],
        [lon + halfLon, lat - halfLat],
        [lon + halfLon, lat + halfLat],
        [lon - halfLon, lat + halfLat],
        [lon - halfLon, lat - halfLat],
      ],
    ],
  };
}

const GEOMETRY_TYPES = new Set(["Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon"]);

/** The record's geometry when it is one the map can draw. */
function drawableGeometry(value: unknown): Geometry | null {
  if (!isRecord(value) || typeof value.type !== "string" || !GEOMETRY_TYPES.has(value.type)) return null;
  if (!Array.isArray(value.coordinates)) return null;
  return value as unknown as Geometry;
}

function feature(geometry: Geometry, imprecise: boolean): Feature {
  return { type: "Feature", geometry, properties: { imprecise } };
}

export function recordShape(record: Pick<RecordOut, "lon" | "lat" | "precision_m" | "geometry">): RecordShape {
  const { lon, lat, precision_m: precision } = record;
  if (isFiniteNumber(precision) && precision >= SQUARE_PRECISION_M) {
    const km = precision === SQUARE_PRECISION_M ? kmSquareAt(lon, lat) : null;
    const polygon: Polygon = km ? { type: "Polygon", coordinates: [km.ring] } : squareAround(lon, lat, precision);
    return {
      collection: { type: "FeatureCollection", features: [feature(polygon, true)] },
      imprecise: true,
      square: km?.ref ?? null,
    };
  }
  const geometry = drawableGeometry(record.geometry) ?? { type: "Point", coordinates: [lon, lat] };
  const features = [feature(geometry, false)];
  // An outline gets its centre marked as well, so a small one still stands out.
  if (geometry.type !== "Point") features.push(feature({ type: "Point", coordinates: [lon, lat] }, false));
  return { collection: { type: "FeatureCollection", features }, imprecise: false, square: null };
}

/** How exact a record's position is, in words. */
export function precisionText(precision: number | null, square: string | null): string {
  if (!isFiniteNumber(precision)) return "The source doesn't say how exact this position is.";
  if (precision >= SQUARE_PRECISION_M) {
    const where = square ? `the one-kilometre square ${square}` : `a square about ${formatMetres(precision)} across`;
    return `Published only to ${where}, so the map shows the square, not a spot.`;
  }
  if (precision <= 1) return "Exact to about a metre.";
  return `Exact to within about ${formatMetres(precision)}.`;
}

function formatMetres(metres: number): string {
  if (metres >= 1000) return `${Number((metres / 1000).toFixed(1))} km`;
  return `${Math.round(metres)} m`;
}

/** The open record's shape, which the map draws over the records layer. */
interface SelectionState {
  shape: FeatureCollection | null;
  setShape: (shape: FeatureCollection | null) => void;
}

export const useRecordSelection = create<SelectionState>()((set) => ({
  shape: null,
  setShape: (shape) => set({ shape }),
}));
