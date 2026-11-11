import type { LiveSourceOut } from "../api.js";

/**
 * The live sources (Decision 0007): indexes we may not store, which the
 * visitor's own browser asks when they look at an area. The server's
 * catalogue says how to ask each one. This turns a catalogue entry into a
 * request for one area, and leaves out the entries this browser can't use:
 * ones that ask for a single record rather than an area, and ones whose
 * address isn't a secure web address on someone else's server.
 */

export interface LiveSource {
  key: string;
  name: string;
  publisher: string;
  licence: string;
  attribution: string;
  coverage: string;
  /** "area" fills a box, "point" the centre of the view. */
  query: "area" | "point";
  pattern: string;
  /** How to link one record to its page on the publisher's site, with `{field}` placeholders. */
  linkTemplate: string | null;
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

/** The catalogue entry as a source this browser can ask, or null when it can't. */
export function liveSourceFrom(item: LiveSourceOut): LiveSource | null {
  const query = queryKind(item.query_pattern);
  if (query === null) return null;
  try {
    // Filled with a real place, so the check is of the address that would be asked.
    liveRequestUrl(
      { key: item.key, query, pattern: item.query_pattern },
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
    licence: item.licence,
    attribution: item.attribution,
    coverage: item.coverage,
    query,
    pattern: item.query_pattern,
    linkTemplate: item.link_template,
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
 */
export function liveRequestUrl(
  source: Pick<LiveSource, "key" | "query" | "pattern">,
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
  return url.href;
}
