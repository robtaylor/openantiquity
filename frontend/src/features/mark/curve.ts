/**
 * The curve `catmull-rom-centripetal-1`, as the server derives it
 * (`backend/src/fieldclub/services/shapes.py`, `derive`). The plan's section
 * "The curve" defines it, and `docs/architecture/curve-vectors.json` holds
 * the paths both implementations are tested against.
 *
 * The server's geometry is what is stored and served. This one draws the
 * preview while a path is being drawn, so it only has to look the same, and
 * the shared vectors keep the two within 1e-7 degrees of each other.
 *
 * Nothing here knows about React or the map, so it can be tested and used alone.
 */

export const CURVE = "catmull-rom-centripetal-1";

export type PointKind = "corner" | "smooth";

export interface PathPoint {
  lon: number;
  lat: number;
  kind: PointKind;
}

/** The least a path is to the curve: its points in order, and whether it closes. */
export interface CurvePath {
  closed: boolean;
  points: readonly PathPoint[];
}

export type CurveGeometry =
  | { type: "LineString"; coordinates: number[][] }
  | { type: "Polygon"; coordinates: number[][][] };

/** An open path needs two points to draw, a closed one three. */
export const MIN_OPEN_POINTS = 2;
export const MIN_CLOSED_POINTS = 3;

/** Points closer than this in the projected plane, in degrees, can't be drawn between. */
export const POINT_MIN_SEPARATION_DEG = 1e-6;

const DECIMALS = 7;
/** About one sample every 33 m along a curved segment, between two and sixteen of them. */
const SAMPLE_SPACING_DEG = 0.0003;
const SAMPLES_MIN = 2;
const SAMPLES_MAX = 16;

type XY = [number, number];

/** Rounded to seven places as the server rounds: to the nearest, of the number's exact value. */
function rounded(value: number): number {
  return Number(value.toFixed(DECIMALS));
}

function steps(length: number): number {
  return Math.min(SAMPLES_MAX, Math.max(SAMPLES_MIN, Math.ceil(length / SAMPLE_SPACING_DEG)));
}

function at(points: readonly PathPoint[], index: number): PathPoint {
  const point = points[index];
  if (point === undefined) throw new RangeError(`A path of ${points.length} points has no point ${index}`);
  return point;
}

/** The scale of a segment's projection: only its own two ends set it. */
function scale(a: PathPoint, b: PathPoint): number {
  return Math.cos((((a.lat + b.lat) / 2) * Math.PI) / 180);
}

/** How far apart two points are in their segment's projected plane, in degrees. */
export function projectedDistance(a: PathPoint, b: PathPoint): number {
  const k = scale(a, b);
  return Math.hypot((b.lon - a.lon) * k, b.lat - a.lat);
}

interface Segment {
  index: number;
  a: PathPoint;
  b: PathPoint;
  /** The neighbours where they are real and used, else null for a phantom. */
  prev: PathPoint | null;
  next: PathPoint | null;
}

function straight(segment: Segment): boolean {
  return segment.a.kind === "corner" && segment.b.kind === "corner";
}

function segments(path: CurvePath): Segment[] {
  const { points, closed } = path;
  const n = points.length;
  const least = closed ? MIN_CLOSED_POINTS : MIN_OPEN_POINTS;
  if (n < least) throw new RangeError(`A${closed ? " closed" : "n open"} path needs ${least} points, not ${n}`);
  const out: Segment[] = [];
  for (let i = 0; i < (closed ? n : n - 1); i++) {
    const j = (i + 1) % n;
    const a = at(points, i);
    const b = at(points, j);
    const hasPrev = closed || i > 0;
    const hasNext = closed || j < n - 1;
    out.push({
      index: i,
      a,
      b,
      prev: a.kind === "smooth" && hasPrev ? at(points, (i - 1 + n) % n) : null,
      next: b.kind === "smooth" && hasNext ? at(points, (j + 1) % n) : null,
    });
  }
  return out;
}

/** How many vertices each segment adds after the first point. Their sum plus one is the size of the geometry. */
export function segmentVertexCounts(path: CurvePath): number[] {
  return segments(path).map((segment) => (straight(segment) ? 1 : steps(projectedDistance(segment.a, segment.b))));
}

function lerp(t: number, ta: number, tb: number, pa: XY, pb: XY): XY {
  const span = tb - ta;
  return [((tb - t) * pa[0] + (t - ta) * pb[0]) / span, ((tb - t) * pa[1] + (t - ta) * pb[1]) / span];
}

/** The vertices a segment adds, ending on its end point, rounded. */
function segmentVertices(segment: Segment): XY[] {
  const { a, b } = segment;
  const end: XY = [b.lon, b.lat];
  if (straight(segment)) return [end];
  const k = scale(a, b);
  const p1: XY = [a.lon * k, a.lat];
  const p2: XY = [b.lon * k, b.lat];
  const p0: XY = segment.prev ? [segment.prev.lon * k, segment.prev.lat] : [2 * p1[0] - p2[0], 2 * p1[1] - p2[1]];
  const p3: XY = segment.next ? [segment.next.lon * k, segment.next.lat] : [2 * p2[0] - p1[0], 2 * p2[1] - p1[1]];
  const d01 = Math.hypot(p1[0] - p0[0], p1[1] - p0[1]);
  const d12 = Math.hypot(p2[0] - p1[0], p2[1] - p1[1]);
  const d23 = Math.hypot(p3[0] - p2[0], p3[1] - p2[1]);
  if (!(Math.min(d01, d12, d23) > 0)) {
    throw new RangeError(`Segment ${segment.index} has two points on top of each other`);
  }
  const t0 = 0;
  const t1 = t0 + Math.sqrt(d01);
  const t2 = t1 + Math.sqrt(d12);
  const t3 = t2 + Math.sqrt(d23);
  const count = steps(d12);
  const out: XY[] = [];
  for (let j = 1; j < count; j++) {
    const t = t1 + ((t2 - t1) * j) / count;
    const a1 = lerp(t, t0, t1, p0, p1);
    const a2 = lerp(t, t1, t2, p1, p2);
    const a3 = lerp(t, t2, t3, p2, p3);
    const b1 = lerp(t, t0, t2, a1, a2);
    const b2 = lerp(t, t1, t3, a2, a3);
    const [x, y] = lerp(t, t1, t2, b1, b2);
    out.push([rounded(x / k), rounded(y)]);
  }
  out.push(end);
  return out;
}

/**
 * The geometry a path draws: a LineString when open, a one-ring Polygon,
 * ending back on its first point, when closed. Throws `RangeError` for a
 * path with too few points, or with two neighbours on top of each other.
 */
export function derive(path: CurvePath): CurveGeometry {
  const list = segments(path);
  const first = at(path.points, 0);
  const vertices: XY[] = [[first.lon, first.lat]];
  for (const segment of list) vertices.push(...segmentVertices(segment));
  if (!path.closed) return { type: "LineString", coordinates: vertices };
  const last = vertices.at(-1);
  if (last?.[0] !== first.lon || last[1] !== first.lat) throw new Error("A closed path must end on its first point");
  return { type: "Polygon", coordinates: [vertices] };
}
