import { ApiError, apiFetch } from "../../api/client.js";
import type { components } from "../../api/schema.js";

/** `GET /geo/search`: the search box's answers. Its query keys live in `searchKeys` and nowhere else. */

export type GeoResult = components["schemas"]["GeoResult"];
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
