import type { Map as MapLibreMap, MapMouseEvent, PointLike } from "maplibre-gl";
import { FINDING_POINT_LAYERS, FINDING_SHAPE_LAYERS } from "./overlayLayers.js";

/**
 * Which finding a tap or click on the map is for (Decision 0031).
 *
 * Candidates are finding markers, lines and areas' edges within reach of the
 * tap, never an area's inside, so whatever lies inside an area stays in
 * reach. The reach is a box round the tap: 6 px for a mouse or a pen, 16 px
 * for a finger. Markers beat lines and lines beat area edges. Among the
 * best kind present the smaller wins only when it is under half the next
 * one's size, a line's length or an area's extent. Two markers in reach, or
 * two alike lines or areas, open the chooser, which lists every candidate
 * in reach in that order.
 *
 * Obscured squares are not candidates: a square is an outline, and Explore
 * handles a tap inside one. Findings win over records.
 */

/** How far from the tap, in pixels, a candidate is still in reach. A pen has a mouse's reach (`reachFor`). */
export const REACH_PX = { mouse: 6, touch: 16 } as const;

/** The smaller of two alike wins only below this share of the other's size. */
export const CLEARLY_SMALLER = 0.5;

export type CandidateKind = "marker" | "line" | "area";

const KIND_ORDER: readonly CandidateKind[] = ["marker", "line", "area"];

export interface FindingCandidate {
  publicId: string;
  kind: CandidateKind;
  /** A line's length or an area's extent. Zero for a marker. */
  size: number;
  /** How far a marker is from the tap, in pixels. Zero for a line or area, which the query reached. */
  distance: number;
  /** Where to put the selection: a marker's point, or the tap for a shape. */
  at: [number, number] | null;
}

export type FindingPick =
  | { kind: "none" }
  | { kind: "one"; candidate: FindingCandidate }
  | { kind: "choose"; candidates: FindingCandidate[] };

/** The markers themselves. The casing under each is drawn with the same filter and adds nothing to pick. */
const MARKER_LAYERS: readonly string[] = [
  FINDING_POINT_LAYERS.points,
  FINDING_POINT_LAYERS.known,
  FINDING_POINT_LAYERS.ruledOut,
];
const SHAPE_LAYERS: readonly string[] = [
  FINDING_SHAPE_LAYERS.lines,
  FINDING_SHAPE_LAYERS.areaEdges,
  FINDING_SHAPE_LAYERS.ruledOut,
];

/** The reach for the kind of pointer that made the tap. Anything not a finger gets a mouse's. */
export function reachFor(pointerType: string | undefined | null): number {
  return pointerType === "touch" ? REACH_PX.touch : REACH_PX.mouse;
}

/**
 * The kind of pointer behind the last press on the page. A click's own event
 * says so where the browser makes clicks pointer events; otherwise the
 * pointer that last went down did it.
 */
let lastPointerType: string | null = null;
if (typeof window !== "undefined") {
  window.addEventListener(
    "pointerdown",
    (event) => {
      lastPointerType = event.pointerType;
    },
    { capture: true, passive: true },
  );
}

/** The kind of pointer behind a map event: "mouse", "pen" or "touch". */
export function pointerTypeOf(event: { originalEvent?: unknown }): string | null {
  const original = event.originalEvent as { pointerType?: unknown } | undefined;
  if (typeof original?.pointerType === "string" && original.pointerType !== "") return original.pointerType;
  return lastPointerType;
}

function kindOf(layerId: string, properties: Record<string, unknown>): CandidateKind | null {
  if (MARKER_LAYERS.includes(layerId)) return "marker";
  if (!SHAPE_LAYERS.includes(layerId)) return null;
  return properties.shape === "area" ? "area" : properties.shape === "line" ? "line" : null;
}

function rank(kind: CandidateKind): number {
  return KIND_ORDER.indexOf(kind);
}

function compare(a: FindingCandidate, b: FindingCandidate): number {
  return rank(a.kind) - rank(b.kind) || a.size - b.size || a.distance - b.distance;
}

/**
 * Every finding within `reach` pixels of `point`, once each, as its most
 * specific kind, in the order the rules rank them.
 */
export function findingCandidatesAt(
  map: MapLibreMap,
  point: { x: number; y: number },
  reach: number,
): FindingCandidate[] {
  const layers = [...MARKER_LAYERS, ...SHAPE_LAYERS].filter((id) => map.getLayer(id) !== undefined);
  if (layers.length === 0) return [];
  const box: [PointLike, PointLike] = [
    [point.x - reach, point.y - reach],
    [point.x + reach, point.y + reach],
  ];
  const found = new Map<string, FindingCandidate>();
  for (const feature of map.queryRenderedFeatures(box, { layers })) {
    const properties = (feature.properties ?? {}) as Record<string, unknown>;
    const publicId = properties.public_id;
    const kind = kindOf(feature.layer.id, properties);
    if (typeof publicId !== "string" || kind === null) continue;
    let at: [number, number] | null = null;
    let distance = 0;
    const geometry = feature.geometry;
    if (kind === "marker" && geometry?.type === "Point" && Array.isArray(geometry.coordinates)) {
      at = [Number(geometry.coordinates[0]), Number(geometry.coordinates[1])];
      const screen = map.project(at);
      distance = Math.hypot(screen.x - point.x, screen.y - point.y);
    }
    const size = kind === "marker" ? 0 : Number(properties.size) || 0;
    const candidate: FindingCandidate = { publicId, kind, size, distance, at };
    const known = found.get(publicId);
    if (!known || compare(candidate, known) < 0) found.set(publicId, candidate);
  }
  return [...found.values()].sort(compare);
}

/** What a tap opens: one finding, the chooser, or nothing of the findings. */
export function pickFinding(candidates: readonly FindingCandidate[]): FindingPick {
  const [first, second] = candidates;
  if (!first) return { kind: "none" };
  if (!second || second.kind !== first.kind) return { kind: "one", candidate: first };
  // Two markers in reach are alike: a silent choice between them would be a guess.
  if (first.kind !== "marker" && second.size > 0 && first.size < second.size * CLEARLY_SMALLER) {
    return { kind: "one", candidate: first };
  }
  return { kind: "choose", candidates: [...candidates] };
}

/** What a tap or click opens, at its own reach. */
export function pickAt(map: MapLibreMap, event: MapMouseEvent): FindingPick {
  return pickFinding(findingCandidatesAt(map, event.point, reachFor(pointerTypeOf(event))));
}

/**
 * True when a finding is within reach of a click, so a record under it is
 * left alone: findings sit above heritage records.
 */
export function findingInReach(map: MapLibreMap, event: MapMouseEvent): boolean {
  return findingCandidatesAt(map, event.point, reachFor(pointerTypeOf(event))).length > 0;
}
