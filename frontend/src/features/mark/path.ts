/**
 * The path a finding is marked by: the tapped points in order, each a corner
 * or a smooth point, and whether the shape is closed. One point is a spot,
 * two or more an open line, and three or more can close into a shape.
 *
 * Every function returns a new path and never changes the one it is given,
 * so a store can hold it as state and keep a history of it. Nothing here
 * knows about React, the map library, or how a path is saved: the drawing
 * tool takes a path and reports a path, and saving it as a finding, a draft
 * or anything later is the caller's business.
 *
 * The limits come from `/meta` (`ShapeLimits`), never from constants here.
 */

import type { ShapeLimits } from "../../api/meta.js";
import {
  type CurveGeometry,
  derive,
  MIN_CLOSED_POINTS,
  MIN_OPEN_POINTS,
  type PathPoint,
  POINT_MIN_SEPARATION_DEG,
  type PointKind,
  projectedDistance,
  segmentVertexCounts,
} from "./curve.js";

export type { PathPoint, PointKind } from "./curve.js";

export type LngLat = [number, number];

export interface Path {
  closed: boolean;
  points: readonly PathPoint[];
}

/** Which end of an open path a tap adds to. */
export type PathEnd = "start" | "end";

export const EMPTY_PATH: Path = { closed: false, points: [] };

/** A tap this close to the far end of an open path, in pixels, closes the shape. */
export const CLOSE_TOLERANCE_PX = 14;

function pointAt(path: Path, index: number): PathPoint {
  const point = path.points[index];
  if (point === undefined) throw new RangeError(`A path of ${path.points.length} points has no point ${index}`);
  return point;
}

function withPoints(path: Path, points: readonly PathPoint[]): Path {
  return { closed: path.closed && points.length >= MIN_CLOSED_POINTS, points };
}

/** The index of one end of the path. */
export function endIndex(path: Path, end: PathEnd): number {
  return end === "start" ? 0 : path.points.length - 1;
}

/** True when the path can be drawn as a line or shape, not just a spot. */
export function isDrawable(path: Path): boolean {
  return path.points.length >= (path.closed ? MIN_CLOSED_POINTS : MIN_OPEN_POINTS);
}

function tooClose(a: PathPoint, b: PathPoint): boolean {
  return projectedDistance(a, b) < POINT_MIN_SEPARATION_DEG;
}

/**
 * Add a point at one end. Nothing changes on a closed shape, at the most
 * points `/meta` allows, or when the point would sit on top of the one it
 * joins, so a double tap on one spot adds one point.
 */
export function addPoint(path: Path, point: PathPoint, end: PathEnd, limits: ShapeLimits): Path {
  if (path.closed || path.points.length >= limits.path_max_points) return path;
  const neighbour = path.points[endIndex(path, end)];
  if (neighbour && tooClose(neighbour, point)) return path;
  return { closed: false, points: end === "start" ? [point, ...path.points] : [...path.points, point] };
}

export function movePoint(path: Path, index: number, [lon, lat]: LngLat): Path {
  const point = pointAt(path, index);
  if (point.lon === lon && point.lat === lat) return path;
  return { closed: path.closed, points: path.points.map((each, i) => (i === index ? { ...point, lon, lat } : each)) };
}

/** Take a point out. A closed shape left with too few points to close opens into a line. */
export function deletePoint(path: Path, index: number): Path {
  pointAt(path, index);
  return withPoints(
    path,
    path.points.filter((_, i) => i !== index),
  );
}

export function setKind(path: Path, index: number, kind: PointKind): Path {
  const point = pointAt(path, index);
  if (point.kind === kind) return path;
  return { closed: path.closed, points: path.points.map((each, i) => (i === index ? { ...point, kind } : each)) };
}

/** A curved point's kind for a straight one, and a straight one's for a curved. */
export function oppositeKind(kind: PointKind): PointKind {
  return kind === "corner" ? "smooth" : "corner";
}

export function switchKind(path: Path, index: number): Path {
  return setKind(path, index, oppositeKind(pointAt(path, index).kind));
}

/** How many segments the path has: one fewer than its points when open, as many when closed. */
function segmentCount(path: Path): number {
  if (!isDrawable(path)) return 0;
  return path.closed ? path.points.length : path.points.length - 1;
}

/**
 * Insert a point half way along the segment after point `index`, on the
 * curve as drawn. It is smooth when either end of the segment is. An open
 * path's last point has no segment after it, and nothing changes.
 */
export function insertAfter(path: Path, index: number): Path {
  pointAt(path, index);
  if (index >= segmentCount(path)) return path;
  const counts = segmentVertexCounts(path);
  const vertices = geometryVertices(drawnGeometry(path));
  const start = counts.slice(0, index).reduce((sum, count) => sum + count, 0);
  const steps = counts[index] ?? 1;
  const a = pointAt(path, index);
  const b = pointAt(path, (index + 1) % path.points.length);
  let middle: LngLat;
  if (steps === 1) {
    middle = [(a.lon + b.lon) / 2, (a.lat + b.lat) / 2];
  } else {
    const low = vertices[start + Math.floor(steps / 2)];
    const high = vertices[start + Math.ceil(steps / 2)];
    if (!low || !high) throw new RangeError(`Segment ${index} has no middle`);
    middle = [(low[0] + high[0]) / 2, (low[1] + high[1]) / 2];
  }
  const kind: PointKind = a.kind === "smooth" || b.kind === "smooth" ? "smooth" : "corner";
  const points = [...path.points];
  points.splice(index + 1, 0, { lon: middle[0], lat: middle[1], kind });
  return { closed: path.closed, points };
}

/** Insert a point at a place, after point `index`: for an Alt-click on the segment that starts there. */
export function insertAt(path: Path, index: number, [lon, lat]: LngLat, kind: PointKind = "corner"): Path {
  pointAt(path, index);
  if (index >= segmentCount(path)) return path;
  const points = [...path.points];
  points.splice(index + 1, 0, { lon, lat, kind });
  return { closed: path.closed, points };
}

type Project = (point: LngLat) => { x: number; y: number };

function distanceToSegmentPx(p: { x: number; y: number }, a: { x: number; y: number }, b: { x: number; y: number }) {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const lengthSquared = dx * dx + dy * dy;
  const t = lengthSquared === 0 ? 0 : Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / lengthSquared));
  return Math.hypot(p.x - (a.x + t * dx), p.y - (a.y + t * dy));
}

/**
 * Which segment of the path, as drawn, passes within `reachPx` of a tap,
 * the nearest if several do, or null. A segment is named by the index of
 * the point it starts from.
 */
export function segmentNear(
  path: Path,
  tap: { x: number; y: number },
  project: Project,
  reachPx: number,
): number | null {
  const geometry = pathGeometry(path);
  if (!geometry) return null;
  const screen = geometryVertices(geometry).map(project);
  const counts = segmentVertexCounts(path);
  let best: number | null = null;
  let bestDistance = reachPx;
  let start = 0;
  counts.forEach((count, segment) => {
    for (let i = start; i < start + count; i++) {
      const a = screen[i];
      const b = screen[i + 1];
      if (!a || !b) continue;
      const distance = distanceToSegmentPx(tap, a, b);
      if (distance <= bestDistance) {
        bestDistance = distance;
        best = segment;
      }
    }
    start += count;
  });
  return best;
}

export function canClose(path: Path): boolean {
  return !path.closed && path.points.length >= MIN_CLOSED_POINTS;
}

/** Join the last point to the first. */
export function closePath(path: Path): Path {
  return canClose(path) ? { closed: true, points: path.points } : path;
}

/** Break a closed shape's closing segment, leaving a line from the first point round to the last. */
export function openPath(path: Path): Path {
  return path.closed ? { closed: false, points: path.points } : path;
}

/**
 * Whether a tap at `tap`, in screen pixels, is on the far end of an open
 * path of three points or more, which closes it. Drawing at the end, the
 * far end is the first point; drawing at the start, the last.
 */
export function closesAt(
  path: Path,
  active: PathEnd,
  tap: { x: number; y: number },
  project: (point: LngLat) => { x: number; y: number },
): boolean {
  if (!canClose(path)) return false;
  const far = pointAt(path, endIndex(path, active === "end" ? "start" : "end"));
  const at = project([far.lon, far.lat]);
  return Math.hypot(at.x - tap.x, at.y - tap.y) <= CLOSE_TOLERANCE_PX;
}

// --------------------------------------------------------------------------
// Undo and redo
// --------------------------------------------------------------------------

/** How many earlier states undo can go back through. */
export const HISTORY_LIMIT = 100;

export interface History<T> {
  past: readonly T[];
  present: T;
  future: readonly T[];
}

export function history<T>(present: T): History<T> {
  return { past: [], present, future: [] };
}

/** Make `next` the present, recording what it replaced. A change that changes nothing records nothing. */
export function commit<T>(states: History<T>, next: T): History<T> {
  if (next === states.present) return states;
  return { past: [...states.past, states.present].slice(-HISTORY_LIMIT), present: next, future: [] };
}

/** Make `next` the present without recording, for each step of a drag after its first. */
export function replace<T>(states: History<T>, next: T): History<T> {
  if (next === states.present) return states;
  return { past: states.past, present: next, future: [] };
}

export function canUndo<T>(states: History<T>): boolean {
  return states.past.length > 0;
}

export function canRedo<T>(states: History<T>): boolean {
  return states.future.length > 0;
}

export function undo<T>(states: History<T>): History<T> {
  const previous = states.past.at(-1);
  if (previous === undefined) return states;
  return { past: states.past.slice(0, -1), present: previous, future: [states.present, ...states.future] };
}

export function redo<T>(states: History<T>): History<T> {
  const [next, ...rest] = states.future;
  if (next === undefined) return states;
  return { past: [...states.past, states.present].slice(-HISTORY_LIMIT), present: next, future: rest };
}

// --------------------------------------------------------------------------
// Measuring, and the limits
// --------------------------------------------------------------------------

const EARTH_RADIUS_M = 6_371_008.8;

function radians(degrees: number): number {
  return (degrees * Math.PI) / 180;
}

/** The distance between two places along the ground, in metres, near enough for the readout and the limits. */
export function groundDistanceM([lon1, lat1]: LngLat, [lon2, lat2]: LngLat): number {
  const dLat = radians(lat2 - lat1);
  const dLon = radians(lon2 - lon1);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(radians(lat1)) * Math.cos(radians(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(h)));
}

/** The geometry's vertices in order: a line's, or a shape's ring with its first point repeated at the end. */
export function geometryVertices(geometry: CurveGeometry | null): LngLat[] {
  if (!geometry) return [];
  return geometry.type === "Polygon" ? (geometry.coordinates[0] ?? []) : geometry.coordinates;
}

/**
 * Each path's geometry, derived once. A path is never changed once made, so
 * the drawing, the length, the anchor and the limits read one derivation
 * between them, and a path that is replaced is forgotten with it.
 */
const geometries = new WeakMap<Path, CurveGeometry | null>();

/** The drawn geometry, or null for a spot or nothing. */
export function pathGeometry(path: Path): CurveGeometry | null {
  const known = geometries.get(path);
  if (known !== undefined) return known;
  const geometry = isDrawable(path) ? derive(path) : null;
  geometries.set(path, geometry);
  return geometry;
}

/** The geometry of a path already known to be drawable. */
function drawnGeometry(path: Path): CurveGeometry {
  const geometry = pathGeometry(path);
  if (!geometry) throw new RangeError(`A path of ${path.points.length} points draws nothing`);
  return geometry;
}

function measure(vertices: readonly LngLat[]): number {
  let total = 0;
  for (let i = 1; i < vertices.length; i++) {
    const a = vertices[i - 1];
    const b = vertices[i];
    if (a && b) total += groundDistanceM(a, b);
  }
  return total;
}

/** A line's length, or a shape's perimeter, in metres, along the curve as drawn. Nothing for a spot. */
export function lengthM(path: Path): number {
  return measure(geometryVertices(pathGeometry(path)));
}

/** The larger of a shape's east–west width at its middle latitude and its north–south height, in metres. */
function acrossM(vertices: readonly LngLat[]): number {
  const lons = vertices.map(([lon]) => lon);
  const lats = vertices.map(([, lat]) => lat);
  const west = Math.min(...lons);
  const east = Math.max(...lons);
  const south = Math.min(...lats);
  const north = Math.max(...lats);
  const middleLat = (south + north) / 2;
  const middleLon = (west + east) / 2;
  return Math.max(
    groundDistanceM([west, middleLat], [east, middleLat]),
    groundDistanceM([middleLon, south], [middleLon, north]),
  );
}

function km(metres: number): string {
  return (metres / 1000).toLocaleString("en-GB", { maximumFractionDigits: 1 });
}

/**
 * Why the server would refuse this path, in plain words, or null when it
 * would take it, so the finder hears at once rather than after a round
 * trip. The server checks again, and its word is final: a closed shape that
 * crosses itself is left to it.
 */
export function pathProblem(path: Path, limits: ShapeLimits): string | null {
  if (path.points.length > limits.path_max_points) {
    return `A line or shape can have at most ${limits.path_max_points.toLocaleString("en-GB")} points.`;
  }
  if (!isDrawable(path)) return null;
  const pairs = path.points.length - (path.closed ? 0 : 1);
  for (let i = 0; i < pairs; i++) {
    if (tooClose(pointAt(path, i), pointAt(path, (i + 1) % path.points.length))) {
      return "Two neighbouring points are on top of each other. Move one, or delete it.";
    }
  }
  const vertexCount = segmentVertexCounts(path).reduce((sum, count) => sum + count, 1);
  if (vertexCount > limits.shape_max_vertices) {
    return "That would draw too fine a curve to keep. Use straight points on the long straight stretches.";
  }
  const vertices = geometryVertices(drawnGeometry(path));
  if (path.closed) {
    if (acrossM(vertices) > limits.shape_max_across_m) {
      return `A closed shape can be at most ${km(limits.shape_max_across_m)} km across.`;
    }
  } else if (measure(vertices) > limits.line_max_length_m) {
    return `A line can be at most ${km(limits.line_max_length_m)} km long.`;
  }
  return null;
}

// --------------------------------------------------------------------------
// Old outlines, and the API's form
// --------------------------------------------------------------------------

function positions(value: unknown): LngLat[] | null {
  if (!Array.isArray(value)) return null;
  const out: LngLat[] = [];
  for (const position of value) {
    if (!Array.isArray(position)) return null;
    const [lon, lat] = position;
    if (typeof lon !== "number" || typeof lat !== "number" || !Number.isFinite(lon) || !Number.isFinite(lat)) {
      return null;
    }
    out.push([lon, lat]);
  }
  return out;
}

function corners(list: readonly LngLat[]): PathPoint[] {
  return list.map(([lon, lat]) => ({ lon, lat, kind: "corner" }));
}

/**
 * An outline drawn before paths existed, read as the all-corner path that
 * draws it: a LineString as an open path, a one-ring Polygon as a closed
 * one without its repeated first point. Anything else, or anything too
 * short or malformed, is null.
 */
export function pathFromOutline(geometry: { type: string; coordinates?: unknown } | null | undefined): Path | null {
  if (!geometry) return null;
  if (geometry.type === "LineString") {
    const line = positions(geometry.coordinates);
    return line && line.length >= MIN_OPEN_POINTS ? { closed: false, points: corners(line) } : null;
  }
  if (geometry.type === "Polygon") {
    const rings = geometry.coordinates;
    if (!Array.isArray(rings) || rings.length !== 1) return null;
    const ring = positions(rings[0]);
    if (!ring || ring.length < MIN_CLOSED_POINTS + 1) return null;
    return { closed: true, points: corners(ring.slice(0, -1)) };
  }
  return null;
}

/** The path as `POST` and `PATCH /findings` take it. The server writes the curve's name. */
export function apiPath(path: Path): { closed: boolean; points: PathPoint[] } {
  return { closed: path.closed, points: path.points.map(({ lon, lat, kind }) => ({ lon, lat, kind })) };
}

// --------------------------------------------------------------------------
// Where a path is
// --------------------------------------------------------------------------

function halfWayAlong(vertices: readonly LngLat[]): LngLat | null {
  const total = measure(vertices);
  let along = 0;
  for (let i = 1; i < vertices.length; i++) {
    const a = vertices[i - 1];
    const b = vertices[i];
    if (!a || !b) continue;
    const piece = groundDistanceM(a, b);
    if (piece > 0 && along + piece >= total / 2) {
      const t = (total / 2 - along) / piece;
      return [a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])];
    }
    along += piece;
  }
  return vertices[0] ?? null;
}

function insideRing([x, y]: LngLat, ring: readonly LngLat[]): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i] ?? [0, 0];
    const [xj, yj] = ring[j] ?? [0, 0];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

/** A ring's centroid when it lies inside, otherwise the middle of the widest stretch across it at that latitude. */
function insidePoint(ring: readonly LngLat[]): LngLat | null {
  let area = 0;
  let cx = 0;
  let cy = 0;
  for (let i = 0; i < ring.length - 1; i++) {
    const [x0, y0] = ring[i] ?? [0, 0];
    const [x1, y1] = ring[i + 1] ?? [0, 0];
    const cross = x0 * y1 - x1 * y0;
    area += cross;
    cx += (x0 + x1) * cross;
    cy += (y0 + y1) * cross;
  }
  if (area === 0) return ring[0] ?? null;
  const centroid: LngLat = [cx / (3 * area), cy / (3 * area)];
  if (insideRing(centroid, ring)) return centroid;
  const crossings: number[] = [];
  for (let i = 0; i < ring.length - 1; i++) {
    const [x0, y0] = ring[i] ?? [0, 0];
    const [x1, y1] = ring[i + 1] ?? [0, 0];
    if (y0 > centroid[1] !== y1 > centroid[1]) crossings.push(x0 + ((centroid[1] - y0) * (x1 - x0)) / (y1 - y0));
  }
  crossings.sort((a, b) => a - b);
  let widest: LngLat | null = null;
  let width = -1;
  for (let i = 0; i + 1 < crossings.length; i += 2) {
    const west = crossings[i] ?? 0;
    const east = crossings[i + 1] ?? 0;
    if (east - west > width) {
      width = east - west;
      widest = [(west + east) / 2, centroid[1]];
    }
  }
  return widest ?? ring[0] ?? null;
}

/**
 * Near where the server will put the finding's anchor: the spot itself, the
 * point half way along a line, or a point inside a shape. The server
 * chooses the real one. This is for the suggested title and the readout
 * before saving.
 */
export function anchorOf(path: Path): LngLat | null {
  const [first] = path.points;
  if (!first) return null;
  const geometry = pathGeometry(path);
  if (!geometry) return [first.lon, first.lat];
  const vertices = geometryVertices(geometry);
  return path.closed ? insidePoint(vertices) : halfWayAlong(vertices);
}

const COMPASS = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"] as const;

/** Which way the active end of an open line lies from its other end, as a point of the compass, or null. */
export function endDirection(path: Path, active: PathEnd): string | null {
  if (path.closed || path.points.length < MIN_OPEN_POINTS) return null;
  const here = pointAt(path, endIndex(path, active));
  const there = pointAt(path, endIndex(path, active === "end" ? "start" : "end"));
  const k = Math.cos(radians((here.lat + there.lat) / 2));
  const east = (here.lon - there.lon) * k;
  const north = here.lat - there.lat;
  if (east === 0 && north === 0) return null;
  const bearing = (Math.atan2(east, north) * 180) / Math.PI;
  return COMPASS[Math.round(((bearing + 360) % 360) / 45) % 8] ?? null;
}
