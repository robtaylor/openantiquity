/**
 * The outline tool: tap to add corners, undo the last one, then close the
 * shape or finish it as a line. A line suits a bank, a ditch or a trackway;
 * a closed shape suits an enclosure or a mound.
 *
 * Every function returns a new outline and never changes the one it is
 * given, so the mark store can hold it as state.
 */

import type { GeoJSONGeometry } from "../findings/types.js";

export type LngLat = [number, number];

/** "drawing" while corners are being added, then "polygon" or "line". */
export type OutlineShape = "drawing" | "polygon" | "line";

export interface Outline {
  points: readonly LngLat[];
  shape: OutlineShape;
}

/** A closed shape needs three corners, a line two. */
export const MIN_POLYGON_POINTS = 3;
export const MIN_LINE_POINTS = 2;

/** The server takes an outline only this close to the marked point, in degrees (about a kilometre). */
export const OUTLINE_MAX_GAP_DEG = 0.01;
/** And only this far across, in degrees: a few kilometres. */
export const OUTLINE_MAX_SPAN_DEG = 0.05;

export const NEW_OUTLINE: Outline = { points: [], shape: "drawing" };

/** Corner `index`, which the caller knows is there. */
function corner(points: readonly LngLat[], index: number): LngLat {
  const point = points[index];
  if (point === undefined) throw new RangeError(`An outline with ${points.length} corners has no corner ${index}`);
  return point;
}

export function addPoint(outline: Outline, point: LngLat): Outline {
  if (outline.shape !== "drawing") return outline;
  return { points: [...outline.points, point], shape: "drawing" };
}

/** Take the last corner away. A finished shape opens up again for drawing. */
export function undoPoint(outline: Outline): Outline {
  if (outline.shape !== "drawing") return { points: outline.points, shape: "drawing" };
  return { points: outline.points.slice(0, -1), shape: "drawing" };
}

export function canClose(outline: Outline): boolean {
  return outline.shape === "drawing" && outline.points.length >= MIN_POLYGON_POINTS;
}

export function canFinishLine(outline: Outline): boolean {
  return outline.shape === "drawing" && outline.points.length >= MIN_LINE_POINTS;
}

export function closeShape(outline: Outline): Outline {
  return canClose(outline) ? { points: outline.points, shape: "polygon" } : outline;
}

export function finishLine(outline: Outline): Outline {
  return canFinishLine(outline) ? { points: outline.points, shape: "line" } : outline;
}

/**
 * The outline as GeoJSON for `POST /findings`, or null when there is not
 * enough of it. One still being drawn is closed if it has three corners and
 * taken as a line if it has two, so pressing save mid-way keeps the work.
 */
export function outlineGeometry(outline: Outline | null): GeoJSONGeometry | null {
  if (outline === null) return null;
  const points = outline.points.map(([lng, lat]): LngLat => [lng, lat]);
  const polygon = outline.shape === "polygon" || (outline.shape === "drawing" && points.length >= MIN_POLYGON_POINTS);
  if (polygon && points.length >= MIN_POLYGON_POINTS) {
    return { type: "Polygon", coordinates: [[...points, corner(points, 0)]] };
  }
  if (points.length >= MIN_LINE_POINTS) return { type: "LineString", coordinates: points };
  return null;
}

/**
 * Why the server would refuse this outline round this point, in plain words,
 * or null when it would take it. Checked before saving, so the person hears
 * at once rather than after a round trip.
 */
export function outlineProblem(outline: Outline | null, point: LngLat): string | null {
  if (outline === null || outline.points.length === 0) return null;
  const lngs = outline.points.map(([lng]) => lng);
  const lats = outline.points.map(([, lat]) => lat);
  const span = Math.max(Math.max(...lngs) - Math.min(...lngs), Math.max(...lats) - Math.min(...lats));
  if (span > OUTLINE_MAX_SPAN_DEG) return "The outline is too big. Keep it to a few kilometres across.";
  if (distanceToOutline(outline, point) > OUTLINE_MAX_GAP_DEG) {
    return "Draw the outline round your mark, or move the mark into it.";
  }
  return null;
}

function distanceToSegment([px, py]: LngLat, [ax, ay]: LngLat, [bx, by]: LngLat): number {
  const dx = bx - ax;
  const dy = by - ay;
  const lengthSquared = dx * dx + dy * dy;
  const t = lengthSquared === 0 ? 0 : Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / lengthSquared));
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}

function insideRing([px, py]: LngLat, ring: readonly LngLat[]): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = corner(ring, i);
    const [xj, yj] = corner(ring, j);
    if (yi > py !== yj > py && px < ((xj - xi) * (py - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

/**
 * How far the point is from the outline in degrees, measured flat as the
 * server measures it: zero inside a closed shape, otherwise to the nearest edge.
 */
export function distanceToOutline(outline: Outline, point: LngLat): number {
  const geometry = outlineGeometry(outline);
  const { points } = outline;
  if (points.length === 1) return distanceToSegment(point, corner(points, 0), corner(points, 0));
  const closed = geometry?.type === "Polygon";
  if (closed && insideRing(point, points)) return 0;
  let nearest = Number.POSITIVE_INFINITY;
  const edges = closed ? points.length : points.length - 1;
  for (let i = 0; i < edges; i++) {
    nearest = Math.min(nearest, distanceToSegment(point, corner(points, i), corner(points, (i + 1) % points.length)));
  }
  return nearest;
}
