import { ApiError, apiFetch } from "../../api/client.js";
import type { components } from "../../api/schema.js";

/** `GET /geo/search`: the search box's answers. Its query keys live in `searchKeys` and nowhere else. */

export type GeoResult = components["schemas"]["GeoResult"];
type SourceRef = components["schemas"]["SourceRef"];
export type GeoResultType = GeoResult["type"];

/** How many places one search asks for. The server allows up to 20. */
export const GEO_SEARCH_LIMIT = 12;

export const searchKeys = {
  geo: (q: string) => ["search", "geo", q] as const,
};

export async function fetchGeoSearch(q: string, signal?: AbortSignal): Promise<GeoResult[]> {
  const body = await apiFetch<components["schemas"]["GeoResults"]>("/geo/search", {
    query: { q, limit: GEO_SEARCH_LIMIT },
    signal,
  });
  return body.items;
}

/** The heading over each kind of result. The kinds are the API's own, from the generated schema. */
export const GROUP_LABELS: Readonly<Record<GeoResultType, string>> = {
  gridref: "Grid reference",
  coordinates: "Coordinates",
  finding: "Findings",
  place: "Places",
  record: "Heritage records",
};

export interface ResultGroup {
  type: GeoResultType;
  label: string;
  /** Each result with its place in the whole list, which is what the arrow keys move through. */
  items: Array<{ result: GeoResult; index: number }>;
}

/**
 * Results grouped by kind. The server sends the best first, so the groups
 * come in the order their first result does, and the arrow keys run through
 * the groups in the order they are shown.
 */
export function groupResults(results: readonly GeoResult[]): { groups: ResultGroup[]; ordered: GeoResult[] } {
  const groups: ResultGroup[] = [];
  for (const result of results) {
    let group = groups.find((candidate) => candidate.type === result.type);
    if (!group) {
      group = { type: result.type, label: GROUP_LABELS[result.type] ?? result.type, items: [] };
      groups.push(group);
    }
    group.items.push({ result, index: -1 });
  }
  const ordered: GeoResult[] = [];
  for (const group of groups) {
    for (const item of group.items) {
      item.index = ordered.length;
      ordered.push(item.result);
    }
  }
  return { groups, ordered };
}

/** Where the map goes for a result: the middle of its box when it has one, at the zoom the server suggests. */
export function cameraFor(result: GeoResult): { lng: number; lat: number; zoom: number } {
  const box = result.bbox;
  if (box && box.length === 4 && box.every(Number.isFinite)) {
    const [west, south, east, north] = box as [number, number, number, number];
    return { lng: (west + east) / 2, lat: (south + north) / 2, zoom: result.zoom };
  }
  return { lng: result.lon, lat: result.lat, zoom: result.zoom };
}

/** True when the server gave up on a search because it took too long. */
export function isSearchTimeout(error: unknown): boolean {
  return error instanceof ApiError && (error.code === "search_timeout" || error.status === 504);
}

/**
 * The longest text the server searches for, in characters. Both search
 * fields stop there, and the server refuses anything longer with a 422.
 * It is the backend's `records.MAX_QUERY_CHARS`.
 */
export const MAX_QUERY_CHARS = 200;

/** True when the server refused the search itself, so asking again would be refused again. */
export function isSearchRefused(error: unknown): boolean {
  return error instanceof ApiError && error.status === 422;
}

/** Text compared loosely: no case, and any run of spaces is one space. */
function loose(text: string): string {
  return text.trim().replace(/\s+/g, " ").toLocaleLowerCase("en-GB");
}

/**
 * Whether Enter, pressed before a result was picked, may go straight to
 * this one, the first. A grid reference, a pair of coordinates and a
 * finding's id are read exactly. A place may be taken only when its name is
 * the whole of what was typed. Anything else is only a likeness, which may
 * be at the other end of the country, so the list is shown instead.
 */
export function takesOnEnter(result: GeoResult, text: string): boolean {
  if (result.type === "gridref" || result.type === "coordinates" || result.type === "finding") return true;
  return result.type === "place" && loose(result.label) === loose(text);
}

/** The sources of the results, each once, in the order they first appear. */
export function resultSources(results: readonly GeoResult[]): SourceRef[] {
  const seen = new Map<string, SourceRef>();
  for (const result of results) {
    if (result.source && !seen.has(result.source.key)) seen.set(result.source.key, result.source);
  }
  return [...seen.values()];
}
