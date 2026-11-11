import { isFiniteNumber, isRecord } from "../../../api/guards.js";
import { safeHref } from "../../../map/attribution.js";

/**
 * Reading what a live source answered. The catalogue describes each
 * source's answer in words, not in a form a program can follow, so this
 * recognises the three kinds of answer the catalogue's sources give: GeoJSON
 * (the ArcGIS map services and others), the Archaeology Data Service's
 * search results, and the MediaWiki API. Anything else is unreadable, and
 * the source says so and stays off.
 *
 * Every value is someone else's. Names are kept as plain text, cut to a
 * sensible length, and links survive only as http or https addresses.
 */

export interface LiveRecord {
  /** Unique within its source. */
  id: string;
  name: string;
  lon: number;
  lat: number;
  /** The record's page on the publisher's site, when the catalogue says how to build it. */
  url: string | null;
}

export interface LiveAnswer {
  records: LiveRecord[];
  /** True when the source sent more than `cap`, and only the first `cap` are kept. */
  truncated: boolean;
}

export class LiveResponseError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "LiveResponseError";
  }
}

/** The most records one live source may put on the map for one view. */
export const MAX_LIVE_RECORDS = 200;
const MAX_NAME_CHARS = 160;

/** Property names that usually hold a record's name, in the order they are tried. */
const NAME_KEYS = ["name", "Name", "NAME", "title", "Title", "TITLE", "SiteName", "SITE_NAME", "MonName"];
/** Property names that usually hold a record's identifier. */
const ID_KEYS = ["MonUID", "monuid", "HER_Refere", "PrefRef", "id", "ID", "Filename", "OBJECTID", "FID"];

type Props = Record<string, unknown>;

function text(value: unknown): string | null {
  if (typeof value === "string") {
    const trimmed = value.replace(/\s+/g, " ").trim();
    return trimmed === "" ? null : trimmed;
  }
  return isFiniteNumber(value) ? String(value) : null;
}

function first(props: Props, keys: readonly string[]): string | null {
  for (const key of keys) {
    const value = text(props[key]);
    if (value !== null) return value;
  }
  return null;
}

function cut(value: string): string {
  return value.length > MAX_NAME_CHARS ? `${value.slice(0, MAX_NAME_CHARS - 1)}…` : value;
}

/**
 * Fill a link template from a record's fields. A template that is a single
 * field stands for an address the record holds itself. Elsewhere each value
 * is encoded, so a field can't change what the address points at. A field
 * can be followed by " lower-case". Anything but an http or https address
 * comes out as null.
 */
export function fillLinkTemplate(template: string | null, props: Props): string | null {
  if (!template) return null;
  const whole = /^\{([^{}]+)\}$/.exec(template.trim());
  const fieldValue = (field: string): string | null => {
    const [name, modifier] = field.trim().split(/\s+/, 2);
    const value = name === undefined ? null : text(props[name]);
    if (value === null) return null;
    return modifier === "lower-case" ? value.toLowerCase() : value;
  };
  if (whole?.[1] !== undefined) return safeHref(fieldValue(whole[1])) ?? null;
  let missing = false;
  const filled = template.replace(/\{([^{}]+)\}/g, (_match, field: string) => {
    const value = fieldValue(field);
    if (value === null) missing = true;
    return encodeURIComponent(value ?? "");
  });
  return missing ? null : (safeHref(filled) ?? null);
}

function isPosition(value: unknown): value is [number, number] {
  return (
    Array.isArray(value) &&
    value.length >= 2 &&
    isFiniteNumber(value[0]) &&
    isFiniteNumber(value[1]) &&
    Math.abs(value[0]) <= 180 &&
    Math.abs(value[1]) <= 90
  );
}

/** A point to draw a geometry at: the point itself, or the middle of the box round it. */
function centreOf(geometry: unknown): [number, number] | null {
  if (!isRecord(geometry)) return null;
  if (geometry.type === "Point") return isPosition(geometry.coordinates) ? geometry.coordinates : null;
  let west = Number.POSITIVE_INFINITY;
  let south = Number.POSITIVE_INFINITY;
  let east = Number.NEGATIVE_INFINITY;
  let north = Number.NEGATIVE_INFINITY;
  const visit = (value: unknown, depth: number): void => {
    if (depth > 4 || !Array.isArray(value)) return;
    if (isPosition(value)) {
      west = Math.min(west, value[0]);
      east = Math.max(east, value[0]);
      south = Math.min(south, value[1]);
      north = Math.max(north, value[1]);
      return;
    }
    for (const item of value) visit(item, depth + 1);
  };
  visit(geometry.coordinates, 0);
  return Number.isFinite(west) ? [(west + east) / 2, (south + north) / 2] : null;
}

interface Candidate {
  id: string | null;
  name: string | null;
  position: [number, number] | null;
  props: Props;
}

function fromGeoJson(body: Props): Candidate[] {
  const features = Array.isArray(body.features) ? body.features : [];
  return features.filter(isRecord).map((feature) => {
    const props = isRecord(feature.properties) ? feature.properties : {};
    return {
      id: text(feature.id) ?? first(props, ID_KEYS),
      name: first(props, NAME_KEYS),
      position: centreOf(feature.geometry),
      props,
    };
  });
}

/** The Archaeology Data Service catalogue: `hits[]` with `data.title` and `data.spatial[].geopoint`. */
function fromSearchHits(hits: unknown[]): Candidate[] {
  return hits.filter(isRecord).map((hit) => {
    const data = isRecord(hit.data) ? hit.data : {};
    const title = isRecord(data.title) ? text(data.title.text) : text(data.title);
    let position: [number, number] | null = null;
    for (const place of Array.isArray(data.spatial) ? data.spatial : []) {
      const point = isRecord(place) && isRecord(place.geopoint) ? place.geopoint : null;
      if (point && isPosition([point.lon, point.lat])) {
        position = [point.lon as number, point.lat as number];
        break;
      }
    }
    const id = text(hit.id);
    return { id, name: title, position, props: { ...data, id } };
  });
}

/** The MediaWiki API: `query.pages{}` with `title` and `coordinates[0]`. */
function fromWikiPages(pages: Props): Candidate[] {
  return Object.values(pages)
    .filter(isRecord)
    .map((page) => {
      const coordinates = Array.isArray(page.coordinates) && isRecord(page.coordinates[0]) ? page.coordinates[0] : {};
      const position: [number, number] | null = isPosition([coordinates.lon, coordinates.lat])
        ? [coordinates.lon as number, coordinates.lat as number]
        : null;
      return { id: text(page.pageid) ?? text(page.title), name: text(page.title), position, props: page };
    });
}

function candidatesOf(body: unknown): Candidate[] {
  if (!isRecord(body)) throw new LiveResponseError("The answer wasn't an object");
  // ArcGIS and MediaWiki both answer some failures with a 200 and an error object.
  if (isRecord(body.error)) {
    throw new LiveResponseError(
      `The source refused the request: ${text(body.error.message) ?? text(body.error.info) ?? text(body.error.code) ?? "no reason given"}`,
    );
  }
  if (body.type === "FeatureCollection") return fromGeoJson(body);
  if (Array.isArray(body.hits)) return fromSearchHits(body.hits);
  if (isRecord(body.query) && isRecord(body.query.pages)) return fromWikiPages(body.query.pages);
  // MediaWiki leaves out `query` altogether when nothing is near.
  if ("batchcomplete" in body) return [];
  throw new LiveResponseError("The answer wasn't in a form Field Club can read");
}

/** Turn a live source's answer into records the map can draw, at most `cap` of them. */
export function parseLiveAnswer(
  body: unknown,
  source: { linkTemplate: string | null },
  cap = MAX_LIVE_RECORDS,
): LiveAnswer {
  const records: LiveRecord[] = [];
  const ids = new Set<string>();
  let drawable = 0;
  for (const candidate of candidatesOf(body)) {
    if (candidate.position === null) continue;
    drawable += 1;
    if (records.length >= cap) continue;
    let id = candidate.id ?? `#${drawable}`;
    // Two records with one id would be one on the map, so the second gets its place in the answer.
    if (ids.has(id)) id = `${id}#${drawable}`;
    ids.add(id);
    records.push({
      id,
      name: cut(candidate.name ?? (candidate.id ? `Record ${candidate.id}` : "A record with no name")),
      lon: candidate.position[0],
      lat: candidate.position[1],
      url: fillLinkTemplate(source.linkTemplate, candidate.props),
    });
  }
  return { records, truncated: drawable > records.length };
}
