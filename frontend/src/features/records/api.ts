import { apiFetch, apiUrl, type QueryValue } from "../../api/client.js";
import type { components } from "../../api/schema.js";

/**
 * The record index, the search box's places and the context catalogue, as
 * the backend serves them. Every shape comes from the generated schema.
 * Query keys for the records feature live in `recordKeys` and nowhere else.
 */

type Schemas = components["schemas"];
export type RecordOut = Schemas["RecordOut"];
export type RecordSummary = Schemas["RecordSummary"];
export type RecordPage = Schemas["RecordPage"];
export type SourceRef = Schemas["SourceRef"];
export type LiveSourceOut = Schemas["LiveSource"];
export type LiveFormat = Schemas["LiveFormat"];
export type LinkShows = Schemas["LinkShows"];
export type ContextLink = Schemas["ContextLink"];
export type ContextLinks = Schemas["ContextLinks"];
export type LinkedFinding = Schemas["LinkedFinding"];
export type LinkedFindingPage = Schemas["Page_LinkedFinding_"];

/** West, south, east, north, in degrees. */
export type Bbox = [number, number, number, number];

/** How many records one page of a search asks for. */
export const SEARCH_PAGE_SIZE = 25;
/** The most one GeoJSON download carries: the backend's largest page. */
export const DOWNLOAD_LIMIT = 200;

export interface RecordQuery {
  q: string;
  /** Source keys. Empty means every source. */
  sources: string[];
  /** Category ids. Empty means every category. */
  categories: string[];
  /** Only records in this box, or null for everywhere. */
  bbox: Bbox | null;
}

export const recordKeys = {
  all: ["records"] as const,
  detail: (id: number) => ["records", "detail", id] as const,
  search: (query: RecordQuery) => ["records", "search", query] as const,
  /** The findings linked to a record. The answer depends on who is asking. */
  findings: (id: number) => ["records", "findings", id] as const,
  liveSources: ["records", "live-sources"] as const,
  /** One live source's answer for one area. These are never sent anywhere, only kept in this page. */
  live: (key: string, area: string) => ["records", "live", key, area] as const,
  links: (lon: number, lat: number, zoom: number) => ["records", "links", lon, lat, zoom] as const,
};

/** A record id from an address: a whole number from 1 up, or null for anything else. */
export function parseRecordId(value: string | undefined): number | null {
  if (value === undefined || !/^[1-9]\d{0,17}$/.test(value)) return null;
  const id = Number(value);
  return Number.isSafeInteger(id) ? id : null;
}

export function fetchRecord(id: number, signal?: AbortSignal): Promise<RecordOut> {
  return apiFetch<RecordOut>(`/records/${id}`, { signal });
}

/** How many linked findings one page of a record's page asks for. */
export const LINKED_FINDINGS_PAGE_SIZE = 20;

/** The findings whose evidence links this record, among those the viewer sees exactly. */
export function fetchRecordFindings(
  id: number,
  cursor: string | null,
  signal?: AbortSignal,
): Promise<LinkedFindingPage> {
  return apiFetch<LinkedFindingPage>(`/records/${id}/findings`, {
    query: { limit: LINKED_FINDINGS_PAGE_SIZE, cursor: cursor ?? undefined },
    signal,
  });
}

/** Rounded to about ten metres, so the server never sees more decimals than a search needs. */
function bboxParam(bbox: Bbox): string {
  return bbox.map((value) => value.toFixed(4)).join(",");
}

function searchParams(query: RecordQuery): Record<string, QueryValue> {
  return {
    q: query.q.trim() || undefined,
    source: query.sources,
    category: query.categories,
    bbox: query.bbox ? bboxParam(query.bbox) : undefined,
  };
}

export function searchRecords(query: RecordQuery, cursor: string | null, signal?: AbortSignal): Promise<RecordPage> {
  return apiFetch<RecordPage>("/records/search", {
    query: { ...searchParams(query), limit: SEARCH_PAGE_SIZE, cursor: cursor ?? undefined },
    signal,
  });
}

/**
 * The address of the same search as a GeoJSON download. The backend puts
 * each record's licence, attribution and reuse class on its feature
 * (Decision 0004), so the file carries them with no work here.
 */
export function recordsDownloadUrl(query: RecordQuery): string {
  return apiUrl("/records/search", { ...searchParams(query), limit: DOWNLOAD_LIMIT, format: "geojson" });
}

export async function fetchLiveSources(signal?: AbortSignal): Promise<LiveSourceOut[]> {
  const body = await apiFetch<Schemas["LiveSources"]>("/context/live-sources", { signal });
  return body.items;
}

export function fetchContextLinks(lon: number, lat: number, zoom: number, signal?: AbortSignal): Promise<ContextLinks> {
  return apiFetch<ContextLinks>("/context/links", { query: { lon, lat, zoom }, signal });
}
