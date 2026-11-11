import type { LiveSourceOut } from "../api.js";
import { type LiveReading, MAX_LIVE_RECORDS, READABLE_FORMATS } from "./parse.js";

/**
 * The live sources (Decision 0007): indexes we may not store, which the
 * visitor's own browser asks when they look at an area. The server's
 * catalogue says how to ask each one. This turns a catalogue entry into a
 * request for one area, and leaves out the entries this browser can't use:
 * ones that ask for a single record rather than an area, ones whose address
 * isn't a secure web address on someone else's server, ones whose answer
 * it has no reader for, and ones it can't credit as their publisher asks
 * (see `creditableOnScreen`).
 */

/**
 * The lowest zoom a source is asked from when the catalogue gives none. A
 * view at zoom 13 is a few kilometres across, which keeps each request small
 * and keeps us from asking someone else's server about a whole county.
 */
export const DEFAULT_LIVE_MIN_ZOOM = 13;

export interface LiveSource extends LiveReading {
  key: string;
  name: string;
  publisher: string;
  /** The credit to show beside its records. Never one that varies by record: see `creditableOnScreen`. */
  attribution: string;
  coverage: string;
  /** "area" fills a box, "point" the centre of the view. */
  query: "area" | "point";
  pattern: string;
  /** How to link one record to its page on the publisher's site, with `{field}` placeholders. */
  linkTemplate: string;
  /** The query parameter that caps how many records the source sends, and the most it allows. */
  limitParam: string | null;
  maxLimit: number | null;
  /** The source is asked nothing while the map is zoomed out further than this. */
  minZoom: number;
}

/** West, south, east and north edges of the view, and its centre, in degrees. */
export interface LiveArea {
  west: number;
  south: number;
  east: number;
  north: number;
}

const AREA_PLACEHOLDERS = ["{west}", "{south}", "{east}", "{north}"];
const POINT_PLACEHOLDERS = ["{lat}", "{lon}"];
const ALL_PLACEHOLDERS = [...AREA_PLACEHOLDERS, ...POINT_PLACEHOLDERS];

export class LiveCatalogueError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "LiveCatalogueError";
  }
}

function queryKind(pattern: string): LiveSource["query"] | null {
  // Anything else in braces, such as a record id, can't be filled in from a view.
  const rest = ALL_PLACEHOLDERS.reduce((text, placeholder) => text.replaceAll(placeholder, ""), pattern);
  if (/[{}]/.test(rest)) return null;
  if (AREA_PLACEHOLDERS.every((placeholder) => pattern.includes(placeholder))) return "area";
  if (POINT_PLACEHOLDERS.every((placeholder) => pattern.includes(placeholder))) return "point";
  return null;
}

/**
 * Words in a catalogue entry's attribution or licence that say the credit
 * or the terms change from record to record: "per record", "per-record
 * Copyright field", "per source HER", "per file", or a clause for "records
 * containing" some other body's data.
 */
const PER_RECORD = /\bper[- ](record|file|source)\b|\brecords? containing\b/i;

/**
 * True when a live source's records can be shown with the credit Decision
 * 0007 asks for, the publisher's name and a link, from what the catalogue
 * gives. The catalogue's attribution and licence are research notes in
 * words, with no machine-readable field naming where a per-record credit
 * is kept, so a source whose credit or terms vary by record can't be
 * credited properly and isn't offered. Nor is one with no link to its
 * records' pages.
 */
export function creditableOnScreen(item: Pick<LiveSourceOut, "attribution" | "licence" | "link_template">): boolean {
  if (!item.link_template?.trim()) return false;
  return !PER_RECORD.test(item.attribution) && !PER_RECORD.test(item.licence);
}

/** The catalogue entry as a source this browser can ask, or null when it can't. */
export function liveSourceFrom(item: LiveSourceOut): LiveSource | null {
  if (!creditableOnScreen(item) || item.link_template === null) return null;
  if (!READABLE_FORMATS.has(item.answer_format)) return null;
  const query = queryKind(item.query_pattern);
  if (query === null) return null;
  try {
    // Filled with a real place, so the check is of the address that would be asked.
    liveRequestUrl(
      { key: item.key, query, pattern: item.query_pattern, limitParam: item.limit_param, maxLimit: item.max_limit },
      { west: -2, south: 51, east: -1.9, north: 51.1 },
      "https://origin.invalid",
    );
  } catch {
    return null;
  }
  return {
    key: item.key,
    name: item.name,
    publisher: item.publisher,
    attribution: item.attribution,
    coverage: item.coverage,
    query,
    pattern: item.query_pattern,
    format: item.answer_format,
    nameField: item.name_field,
    idField: item.id_field,
    linkTemplate: item.link_template,
    limitParam: item.limit_param,
    maxLimit: item.max_limit,
    minZoom: item.min_zoom ?? DEFAULT_LIVE_MIN_ZOOM,
  };
}

export function liveSourcesFrom(items: readonly LiveSourceOut[]): LiveSource[] {
  const seen = new Set<string>();
  const sources: LiveSource[] = [];
  for (const item of items) {
    const source = liveSourceFrom(item);
    if (source && !seen.has(source.key)) {
      seen.add(source.key);
      sources.push(source);
    }
  }
  return sources;
}

function degrees(value: number): string {
  if (!Number.isFinite(value)) throw new LiveCatalogueError(`A live query was given ${value} for a position`);
  return value.toFixed(5);
}

/**
 * The address to ask for an area. It must be https and must not be our own
 * server: what a live source holds is never sent to, or through, Field Club.
 * Where the source has a cap parameter, it asks for one more record than the
 * map draws, so a fuller answer is known to be cut short, and never more
 * than the source allows.
 */
export function liveRequestUrl(
  source: Pick<LiveSource, "key" | "query" | "pattern" | "limitParam" | "maxLimit">,
  area: LiveArea,
  ownOrigin: string = window.location.origin,
): string {
  const centre = { lon: (area.west + area.east) / 2, lat: (area.south + area.north) / 2 };
  const values: Record<string, string> = {
    "{west}": degrees(area.west),
    "{south}": degrees(area.south),
    "{east}": degrees(area.east),
    "{north}": degrees(area.north),
    "{lat}": degrees(centre.lat),
    "{lon}": degrees(centre.lon),
  };
  const filled = Object.entries(values).reduce((text, [key, value]) => text.replaceAll(key, value), source.pattern);
  let url: URL;
  try {
    url = new URL(filled);
  } catch {
    throw new LiveCatalogueError(`Live source ${source.key} has an address that isn't a web address`);
  }
  if (url.protocol !== "https:") throw new LiveCatalogueError(`Live source ${source.key} isn't on https`);
  if (url.origin === new URL(ownOrigin).origin) {
    throw new LiveCatalogueError(`Live source ${source.key} points at this site, which must never hold live data`);
  }
  if (source.limitParam) {
    const wanted = MAX_LIVE_RECORDS + 1;
    url.searchParams.set(source.limitParam, String(source.maxLimit ? Math.min(source.maxLimit, wanted) : wanted));
  }
  return url.href;
}
