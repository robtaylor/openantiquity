import { isFiniteNumber, isRecord } from "../../../api/guards.js";
import { safeHref } from "../../../map/attribution.js";

/**
 * Reading what a live source answered. The catalogue says how to read each
 * source (Decision 0007): the format of its answer, and the fields that hold
 * a record's name and id. Each format has one reader here, GeoJSON (the
 * ArcGIS map services and others), the Archaeology Data Service's search
 * results and the MediaWiki API, and an answer that doesn't fit its reader
 * is unreadable: the source says so and stays off. Names and ids are read
 * only from the fields the catalogue names.
 *
 * Every value is someone else's. Names are kept as plain text, cut to a
 * sensible length, and links survive only as http or https addresses.
 */

import type { LiveFormat } from "../api.js";

/** The formats this browser has a reader for. Others aren't offered. */
export const READABLE_FORMATS: ReadonlySet<LiveFormat> = new Set(["geojson", "ads_search", "mediawiki_query"]);

/** What the catalogue says about reading one source's answer. */
export interface LiveReading {
  format: LiveFormat;
  /** A dotted path, such as "data.title.text", within one record. Null when the source names none. */
  nameField: string | null;
  idField: string | null;
  /**
   * Where the terms ask for a credit or licence taken from each record, the
   * dotted paths to it. `preferredCreditField` is shown in place of
   * `creditField` when a record has it. Absent or null when the source is
   * credited as a whole.
   */
  creditField?: string | null;
  preferredCreditField?: string | null;
  licenceField?: string | null;
  linkTemplate: string | null;
}

export interface LiveRecord {
  /** Unique within its source. */
  id: string;
  name: string;
  lon: number;
  lat: number;
  /** The record's page on the publisher's site, when the catalogue says how to build it. */
  url: string | null;
  /** The record's own credit and licence, as plain text, where the source's terms ask for them. */
  credit: string | null;
  licence: string | null;
}

export interface LiveAnswer {
  records: LiveRecord[];
  /** True when the source sent more than `cap`, of which only the first `cap` are kept, or said it had more than it sent. */
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

type Props = Record<string, unknown>;

function text(value: unknown): string | null {
  if (typeof value === "string") {
    const trimmed = value.replace(/\s+/g, " ").trim();
    return trimmed === "" ? null : trimmed;
  }
  return isFiniteNumber(value) ? String(value) : null;
}

/** The value at a dotted path such as "data.title.text" or "imageinfo.0.extmetadata", or undefined. */
function valueAt(record: Props, path: string | null | undefined): unknown {
  if (!path) return undefined;
  let value: unknown = record;
  for (const part of path.split(".")) {
    // A part that is a number indexes a list.
    if (Array.isArray(value) && /^\d+$/.test(part)) value = value[Number(part)];
    else if (isRecord(value)) value = value[part];
    else return undefined;
  }
  return value;
}

/** The value at a dotted path, as text, or null. */
export function fieldAt(record: Props, path: string | null | undefined): string | null {
  return text(valueAt(record, path));
}

/**
 * A credit or licence from a record, which some sources write as HTML (the
 * Commons' `extmetadata` does), as plain text. Parsing it into an inert
 * document runs nothing and fetches nothing, and only its text is kept.
 */
function creditAt(record: Props, path: string | null | undefined): string | null {
  const value = fieldAt(record, path);
  if (value === null) return null;
  const plain = value.includes("<") ? htmlText(value) : value;
  return plain === null ? null : cut(plain);
}

function htmlText(html: string): string | null {
  const parsed = new DOMParser().parseFromString(html, "text/html");
  for (const element of parsed.querySelectorAll("script, style")) element.remove();
  return text(parsed.body.textContent);
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

interface Candidates {
  candidates: Candidate[];
  /** True when the source says it held back records it had. */
  heldBack: boolean;
}

function candidate(record: Props, reading: LiveReading, position: [number, number] | null, ownId?: unknown): Candidate {
  return {
    id: fieldAt(record, reading.idField) ?? text(ownId),
    name: fieldAt(record, reading.nameField),
    position,
    props: record,
  };
}

/** GeoJSON: names and ids are among each feature's properties. ArcGIS says when it held some back. */
function fromGeoJson(body: Props, reading: LiveReading): Candidates {
  if (body.type !== "FeatureCollection" || !Array.isArray(body.features)) {
    throw new LiveResponseError("The answer wasn't GeoJSON");
  }
  const candidates = body.features.filter(isRecord).map((feature) => {
    const props = isRecord(feature.properties) ? feature.properties : {};
    return candidate(props, reading, centreOf(feature.geometry), feature.id);
  });
  const heldBack =
    body.exceededTransferLimit === true ||
    (isRecord(body.properties) && body.properties.exceededTransferLimit === true);
  return { candidates, heldBack };
}

/** The Archaeology Data Service catalogue: `hits[]`, each placed by `data.spatial[].geopoint`, and `total.value`. */
function fromSearchHits(body: Props, reading: LiveReading): Candidates {
  if (!Array.isArray(body.hits)) throw new LiveResponseError("The answer had no search hits");
  const hits = body.hits.filter(isRecord);
  const candidates = hits.map((hit) => {
    const data = isRecord(hit.data) ? hit.data : {};
    let position: [number, number] | null = null;
    for (const place of Array.isArray(data.spatial) ? data.spatial : []) {
      const point = isRecord(place) && isRecord(place.geopoint) ? place.geopoint : null;
      if (point && isPosition([point.lon, point.lat])) {
        position = [point.lon as number, point.lat as number];
        break;
      }
    }
    return candidate(hit, reading, position);
  });
  const total = isRecord(body.total) && isFiniteNumber(body.total.value) ? body.total.value : hits.length;
  return { candidates, heldBack: total > hits.length };
}

/** The MediaWiki API: `query.pages{}`, each placed by `coordinates[0]`. It leaves out `query` when nothing is near. */
function fromWikiPages(body: Props, reading: LiveReading): Candidates {
  if (!isRecord(body.query)) {
    if ("batchcomplete" in body) return { candidates: [], heldBack: false };
    throw new LiveResponseError("The answer had no query");
  }
  const pages = isRecord(body.query.pages) ? body.query.pages : {};
  const candidates = Object.values(pages)
    .filter(isRecord)
    .map((page) => {
      const coordinates = Array.isArray(page.coordinates) && isRecord(page.coordinates[0]) ? page.coordinates[0] : {};
      const position: [number, number] | null = isPosition([coordinates.lon, coordinates.lat])
        ? [coordinates.lon as number, coordinates.lat as number]
        : null;
      return candidate(page, reading, position, page.pageid);
    });
  return { candidates, heldBack: "continue" in body };
}

function candidatesOf(body: unknown, reading: LiveReading): Candidates {
  if (!isRecord(body)) throw new LiveResponseError("The answer wasn't an object");
  // ArcGIS and MediaWiki both answer some failures with a 200 and an error object.
  if (isRecord(body.error)) {
    throw new LiveResponseError(
      `The source refused the request: ${text(body.error.message) ?? text(body.error.info) ?? text(body.error.code) ?? "no reason given"}`,
    );
  }
  switch (reading.format) {
    case "geojson":
      return fromGeoJson(body, reading);
    case "ads_search":
      return fromSearchHits(body, reading);
    case "mediawiki_query":
      return fromWikiPages(body, reading);
    default:
      throw new LiveResponseError(`OpenAntiquity can't read answers in the form "${reading.format}"`);
  }
}

/** Turn a live source's answer into records the map can draw, at most `cap` of them. */
export function parseLiveAnswer(body: unknown, reading: LiveReading, cap = MAX_LIVE_RECORDS): LiveAnswer {
  const records: LiveRecord[] = [];
  const ids = new Set<string>();
  let drawable = 0;
  const { candidates, heldBack } = candidatesOf(body, reading);
  for (const candidate of candidates) {
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
      url: fillLinkTemplate(reading.linkTemplate, candidate.props),
      credit: creditAt(candidate.props, reading.preferredCreditField) ?? creditAt(candidate.props, reading.creditField),
      licence: creditAt(candidate.props, reading.licenceField),
    });
  }
  return { records, truncated: heldBack || drawable > records.length };
}
