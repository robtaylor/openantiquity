import { apiFetch } from "../../../api/client.js";
import { isFiniteNumber, isRecord } from "../../../api/guards.js";
import { gridMetresToWgs84, wgs84ToGridMetres } from "../../../map/gridref.js";

/**
 * Where one-metre elevation exists, from `GET /terrain/coverage`, and the
 * squares in view where it doesn't. The schema types the answer as unknown,
 * so it is checked here as it arrives.
 */

export class CoverageError extends Error {
  constructor(message: string) {
    super(`Unexpected /terrain/coverage answer: ${message}`);
    this.name = "CoverageError";
  }
}

/** West, south, east, north in degrees. */
export type Bounds = [number, number, number, number];
export type Ring = Array<[number, number]>;

export interface CoverageTile {
  tile: string;
  /** What the data is, such as "2022 composite", when the API says. */
  capture: string | null;
  resolutionM: number | null;
  ring: Ring;
  bounds: Bounds;
}

function ringBounds(ring: Ring): Bounds {
  const lngs = ring.map((point) => point[0]);
  const lats = ring.map((point) => point[1]);
  return [Math.min(...lngs), Math.min(...lats), Math.max(...lngs), Math.max(...lats)];
}

function isPosition(value: unknown): value is [number, number] {
  return Array.isArray(value) && value.length >= 2 && isFiniteNumber(value[0]) && isFiniteNumber(value[1]);
}

export function parseCoverage(value: unknown): CoverageTile[] {
  if (!isRecord(value) || value.type !== "FeatureCollection" || !Array.isArray(value.features)) {
    throw new CoverageError("not a FeatureCollection");
  }
  return value.features.map((feature: unknown, index) => {
    if (!isRecord(feature) || !isRecord(feature.geometry) || feature.geometry.type !== "Polygon") {
      throw new CoverageError(`feature ${index} is not a polygon`);
    }
    const rings = feature.geometry.coordinates;
    const outer = Array.isArray(rings) ? rings[0] : undefined;
    if (!Array.isArray(outer) || outer.length < 4 || !outer.every(isPosition)) {
      throw new CoverageError(`feature ${index} has no outer ring`);
    }
    const ring = outer.map(([lng, lat]: [number, number]): [number, number] => [lng, lat]);
    const props = isRecord(feature.properties) ? feature.properties : {};
    return {
      tile: typeof props.tile === "string" ? props.tile : String(feature.id ?? index),
      capture: typeof props.capture === "string" && props.capture !== "" ? props.capture : null,
      resolutionM: isFiniteNumber(props.resolution_m) ? props.resolution_m : null,
      ring,
      bounds: ringBounds(ring),
    };
  });
}

/** Coverage is asked for on a grid this many degrees across, so small moves reuse an answer. */
const BOX_STEP = 0.25;

/** The box to ask about for a view: the view's bounds pushed out to the grid. */
export function coverageBox([west, south, east, north]: Bounds): Bounds {
  const down = (value: number) => Math.floor(value / BOX_STEP) * BOX_STEP;
  const up = (value: number) => Math.ceil(value / BOX_STEP) * BOX_STEP;
  return [Math.max(-180, down(west)), Math.max(-90, down(south)), Math.min(180, up(east)), Math.min(90, up(north))];
}

export async function fetchCoverage(box: Bounds, signal?: AbortSignal): Promise<CoverageTile[]> {
  return parseCoverage(await apiFetch<unknown>("/terrain/coverage", { query: { bbox: box.join(",") }, signal }));
}

function overlaps(a: Bounds, b: Bounds): boolean {
  return a[0] <= b[2] && a[2] >= b[0] && a[1] <= b[3] && a[3] >= b[1];
}

/** Ray casting: true when the point is inside the ring. */
export function insideRing([x, y]: [number, number], ring: Ring): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i] as [number, number];
    const [xj, yj] = ring[j] as [number, number];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

/** The capture descriptions of the tiles that touch a view, in the order the API gave them. */
export function capturesIn(tiles: readonly CoverageTile[], view: Bounds): string[] {
  const found: string[] = [];
  for (const tile of tiles) {
    if (tile.capture !== null && overlaps(tile.bounds, view) && !found.includes(tile.capture)) found.push(tile.capture);
  }
  return found;
}

/** The elevation is mirrored in 5 km squares of the British National Grid. */
export const CELL_M = 5000;
/** More cells than this and the view is too wide to shade square by square. */
export const MAX_CELLS = 900;
const GRID_EAST_M = 700_000;
const GRID_NORTH_M = 1_300_000;

export interface Gaps {
  /** The 5 km squares in view that have no coverage, as closed rings. */
  rings: Ring[];
  /** How many squares the view touches in all. */
  cells: number;
}

/**
 * The 5 km British National Grid squares in a view that no coverage tile
 * holds, so the map can say "no data here" instead of drawing nothing. A
 * square counts as covered when its middle is inside a tile. Null when the
 * view touches more than `MAX_CELLS` squares, or none of the grid.
 */
export function gapsIn(view: Bounds, tiles: readonly CoverageTile[]): Gaps | null {
  const [west, south, east, north] = view;
  const midLng = (west + east) / 2;
  const midLat = (south + north) / 2;
  const edge: Array<[number, number]> = [
    [west, south],
    [east, south],
    [east, north],
    [west, north],
    [midLng, south],
    [midLng, north],
    [west, midLat],
    [east, midLat],
  ];
  const grid = edge.map(([lng, lat]) => wgs84ToGridMetres(lng, lat, "british"));
  const minE = Math.max(0, Math.floor(Math.min(...grid.map((p) => p.easting)) / CELL_M) * CELL_M);
  const minN = Math.max(0, Math.floor(Math.min(...grid.map((p) => p.northing)) / CELL_M) * CELL_M);
  const maxE = Math.min(GRID_EAST_M, Math.ceil(Math.max(...grid.map((p) => p.easting)) / CELL_M) * CELL_M);
  const maxN = Math.min(GRID_NORTH_M, Math.ceil(Math.max(...grid.map((p) => p.northing)) / CELL_M) * CELL_M);
  if (maxE <= minE || maxN <= minN) return null;
  const cells = ((maxE - minE) / CELL_M) * ((maxN - minN) / CELL_M);
  if (cells > MAX_CELLS) return null;

  const corner = (easting: number, northing: number): [number, number] => {
    const { lon, lat } = gridMetresToWgs84({ grid: "british", easting, northing });
    return [lon, lat];
  };
  const nearby = tiles.filter((tile) => overlaps(tile.bounds, view));
  const rings: Ring[] = [];
  for (let e = minE; e < maxE; e += CELL_M) {
    for (let n = minN; n < maxN; n += CELL_M) {
      const middle = corner(e + CELL_M / 2, n + CELL_M / 2);
      const covered = nearby.some((tile) => insideRing(middle, tile.ring));
      if (covered) continue;
      const sw = corner(e, n);
      rings.push([sw, corner(e + CELL_M, n), corner(e + CELL_M, n + CELL_M), corner(e, n + CELL_M), sw]);
    }
  }
  return { rings, cells };
}
