/**
 * An investigation's area: the part of the map it is about, a Polygon or
 * MultiPolygon. A public investigation is found by it on the map. The page
 * of the open investigation puts its area here, and the map draws it.
 */

import { create } from "zustand";
import { isFiniteNumber } from "../../api/guards.js";
import type { GeoJSONGeometry } from "../findings/types.js";

type Ring = Array<[number, number]>;

export interface AreaShape {
  type: "Polygon" | "MultiPolygon";
  /** Every ring of every polygon, as longitude and latitude pairs. */
  rings: Ring[];
}

function ringOf(value: unknown): Ring | null {
  if (!Array.isArray(value) || value.length < 4) return null;
  const ring: Ring = [];
  for (const point of value) {
    if (!Array.isArray(point) || !isFiniteNumber(point[0]) || !isFiniteNumber(point[1])) return null;
    ring.push([point[0], point[1]]);
  }
  return ring;
}

/** The area's rings, or null for no area or a geometry the map can't draw as one. */
export function areaShape(geometry: GeoJSONGeometry | null | undefined): AreaShape | null {
  if (!geometry || !Array.isArray(geometry.coordinates)) return null;
  const polygons: unknown[] =
    geometry.type === "Polygon" ? [geometry.coordinates] : geometry.type === "MultiPolygon" ? geometry.coordinates : [];
  const rings: Ring[] = [];
  for (const polygon of polygons) {
    if (!Array.isArray(polygon)) return null;
    for (const value of polygon) {
      const ring = ringOf(value);
      if (!ring) return null;
      rings.push(ring);
    }
  }
  return rings.length > 0 ? { type: geometry.type as AreaShape["type"], rings } : null;
}

/** West, south, east, north. */
export type Bounds = [number, number, number, number];

export function boundsOf(shape: AreaShape): Bounds {
  const lngs = shape.rings.flatMap((ring) => ring.map(([lng]) => lng));
  const lats = shape.rings.flatMap((ring) => ring.map(([, lat]) => lat));
  return [Math.min(...lngs), Math.min(...lats), Math.max(...lngs), Math.max(...lats)];
}

/** Five decimal places is about a metre, as close as an area needs. */
function fixed(value: number): number {
  return Number(value.toFixed(5));
}

/** A box as the polygon an investigation's area is sent as. */
export function polygonOf([west, south, east, north]: Bounds): GeoJSONGeometry {
  const [w, s, e, n] = [fixed(west), fixed(south), fixed(east), fixed(north)];
  return {
    type: "Polygon",
    coordinates: [
      [
        [w, s],
        [e, s],
        [e, n],
        [w, n],
        [w, s],
      ],
    ],
  };
}

/** A box as a `bbox` parameter, rounded to about a hundred metres so a small pan asks nothing new. */
export function bboxParam([west, south, east, north]: Bounds): string {
  const round = (value: number, toward: (n: number) => number) => (toward(value * 1000) / 1000).toFixed(3);
  return [round(west, Math.floor), round(south, Math.floor), round(east, Math.ceil), round(north, Math.ceil)].join(",");
}

interface AreaState {
  /** The area the open investigation covers, drawn on the map. */
  shape: AreaShape | null;
  setShape: (shape: AreaShape | null) => void;
}

export const useInvestigationArea = create<AreaState>()((set) => ({
  shape: null,
  setShape: (shape) => set({ shape }),
}));
