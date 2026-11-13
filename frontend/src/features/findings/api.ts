import { apiFetch } from "../../api/client.js";
import { type FindingFilters, filterParams, NO_FILTERS } from "./filters.js";
import {
  type FindingCollection,
  type FindingCreate,
  type FindingDetail,
  type FindingPage,
  parseFindingCollection,
  parseFindingPage,
} from "./types.js";

/** West, south, east, north, in degrees. */
export type Bbox = [number, number, number, number];

export const FINDINGS_PATH = "/findings";

/**
 * Half the side of a grid square, in metres. The server matches obscured
 * findings by the centre of their square, so a square that covers the view
 * can have its centre this far outside it.
 */
const HALF_SQUARE_M = 500;
const METRES_PER_DEGREE_LAT = 111_320;

/**
 * The box sent to the server. It is the view widened by half a grid square on
 * each side, so that a square whose centre is off screen but whose body
 * covers the view is still fetched. It is then widened to whole thousandths
 * of a degree (about 100 m). Small drags then ask for the same box, which the
 * query cache already holds, and the server never sees more decimals than it
 * needs.
 */
export function snapBbox([west, south, east, north]: Bbox): Bbox {
  const step = 1000;
  const padLat = HALF_SQUARE_M / METRES_PER_DEGREE_LAT;
  // A degree of longitude is shorter further from the equator, so pad for the edge furthest from it.
  const cosLat = Math.max(0.2, Math.cos((Math.max(Math.abs(south), Math.abs(north)) * Math.PI) / 180));
  const padLon = padLat / cosLat;
  return [
    Math.max(-180, Math.floor((west - padLon) * step) / step),
    Math.max(-90, Math.floor((south - padLat) * step) / step),
    Math.min(180, Math.ceil((east + padLon) * step) / step),
    Math.min(90, Math.ceil((north + padLat) * step) / step),
  ];
}

export function bboxParam(bbox: Bbox): string {
  return bbox.map((value) => String(value)).join(",");
}

/** The box a `bboxParam` string stands for. */
export function parseBboxParam(text: string): Bbox {
  const parts = text.split(",").map(Number);
  const [west, south, east, north] = parts;
  if (parts.length !== 4 || west === undefined || south === undefined || east === undefined || north === undefined) {
    throw new RangeError(`"${text}" is not a box`);
  }
  return [west, south, east, north];
}

function checkBox([west, south, east, north]: Bbox): void {
  if (!(west < east && south < north)) throw new RangeError(`A findings box must run west to east and south to north`);
}

/** The zooms `GET /findings?format=geojson` takes, between which it chooses how far to simplify each shape. */
export const SHAPE_ZOOMS = { min: 9, max: 22 } as const;

/** A map's zoom as the findings box takes it: a whole number from 9 to 22. */
export function shapeZoom(zoom: number): number {
  return Math.min(SHAPE_ZOOMS.max, Math.max(SHAPE_ZOOMS.min, Math.floor(zoom)));
}

/** `GET /findings?bbox=&format=geojson&zoom=`: the findings in a box, as this viewer may see them. */
export async function fetchFindingsInBox(
  bbox: Bbox,
  signal?: AbortSignal,
  filters: FindingFilters = NO_FILTERS,
  zoom: number | null = null,
): Promise<FindingCollection> {
  checkBox(bbox);
  const body = await apiFetch<unknown>(FINDINGS_PATH, {
    query: {
      bbox: bboxParam(bbox),
      format: "geojson",
      ...(zoom === null ? {} : { zoom: shapeZoom(zoom) }),
      ...filterParams(filters),
    },
    signal,
  });
  return parseFindingCollection(body);
}

/** How many findings the Explore list asks for at a time. */
export const FINDINGS_PAGE_SIZE = 30;

/** `GET /findings?bbox=`: one page of the findings in a box, newest first. */
export async function fetchFindingsPage(
  bbox: Bbox,
  filters: FindingFilters,
  cursor: string | null,
  signal?: AbortSignal,
): Promise<FindingPage> {
  checkBox(bbox);
  const body = await apiFetch<unknown>(FINDINGS_PATH, {
    query: { bbox: bboxParam(bbox), limit: FINDINGS_PAGE_SIZE, cursor, ...filterParams(filters) },
    signal,
  });
  return parseFindingPage(body);
}

/** `POST /findings`. The server answers with the new finding's page. */
export function createFinding(body: FindingCreate): Promise<FindingDetail> {
  return apiFetch<FindingDetail>(FINDINGS_PATH, { method: "POST", body });
}
