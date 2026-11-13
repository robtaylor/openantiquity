/**
 * Findings as the frontend receives them. Every shape comes from the
 * generated `schema.d.ts`; this file only names them and checks the map's
 * GeoJSON at run time.
 *
 * What a viewer is sent depends on who they are (Decision 0005), so the map
 * and the list draw only what each finding says about itself. A finding with
 * `obscured` set stands for one whose exact position this viewer may not
 * see. Its point is the centre of a one-kilometre grid square and it has no
 * outline. Whether that happens is the server's decision. The frontend never
 * works it out from the sensitivity level.
 */

import { isFiniteNumber, isRecord } from "../../api/guards.js";
import type { components } from "../../api/schema.js";

type Schemas = components["schemas"];

/** How closely a finding's position is guarded. See docs/ARCHITECTURE.md, "Location sensitivity". */
export type Sensitivity = Schemas["Sensitivity"];
export type FindingSummary = Schemas["FindingSummary"];
export type FindingDetail = Schemas["FindingDetail"];
export type FindingCreate = Schemas["FindingCreate"];
export type FindingPage = Schemas["Page_FindingSummary_"];
export type ViewState = Schemas["ViewState"];
export type GeoJSONGeometry = Schemas["GeoJSONGeometry"];
/** A finding's position as this viewer may see it. */
export type FindingLocation = Schemas["Location"];
export type FeatureClassId = Schemas["FeatureClass"];
export type PeriodId = Schemas["Period"];
export type TierId = Schemas["Tier"];
export type StateId = Schemas["FindingState"];

/** Every level, lowest first. The schema's union, checked against this list by the compiler. */
export const SENSITIVITIES = ["open", "protected"] as const satisfies readonly Sensitivity[];

/** The levels above (`step` 1) or below (-1) `level`, nearest first. */
export function levelsBeside(level: Sensitivity, step: 1 | -1): Sensitivity[] {
  const rank = SENSITIVITIES.indexOf(level);
  const beside = SENSITIVITIES.filter((_, index) => (index - rank) * step > 0);
  return step > 0 ? beside : beside.reverse();
}

export function isSensitivity(value: unknown): value is Sensitivity {
  return (SENSITIVITIES as readonly unknown[]).includes(value);
}

type WireProperties = Schemas["FindingFeatureProperties"];

/**
 * A map feature's properties, trimmed to what the map uses. Tier, state and
 * class are kept as text rather than the schema's unions, so a value newer
 * than this build still draws, in the fallback colour. Sensitivity is left
 * out when the server sends a level this build does not know.
 */
/**
 * A finding's line or area as the map draws it: `properties.shape` of
 * `GET /findings?format=geojson`, clipped to the box and simplified for the
 * zoom asked for. Clipping can cut a line into several, or an area into
 * several parts. Sent only to someone who sees the finding exactly.
 */
export type FindingShape =
  | { type: "LineString"; coordinates: [number, number][] }
  | { type: "MultiLineString"; coordinates: [number, number][][] }
  | { type: "Polygon"; coordinates: [number, number][][] }
  | { type: "MultiPolygon"; coordinates: [number, number][][][] };

export interface FindingProperties extends Pick<WireProperties, "public_id" | "obscured"> {
  tier: string;
  state: string;
  sensitivity?: Sensitivity;
  /** The square's reference, such as "SU1069", when `obscured` is set. */
  square?: string;
  title?: string;
  feature_class?: string;
  /** The line or area, for an exact finding that has one. Never set when `obscured` is. */
  shape?: FindingShape;
}

export interface FindingFeature {
  type: "Feature";
  id?: string | number;
  geometry: { type: "Point"; coordinates: [number, number] };
  properties: FindingProperties;
}

export interface FindingCollection {
  type: "FeatureCollection";
  features: FindingFeature[];
  /**
   * Set when more findings matched than were sent. The map draws what came
   * and says that some were left out. Null or absent when the answer is whole.
   */
  next_cursor?: string | null;
}

/** Shared. Never modify it. */
export const NO_FINDINGS: FindingCollection = { type: "FeatureCollection", features: [] };

export class FindingsResponseError extends Error {
  constructor(message: string) {
    super(`Unexpected findings response: ${message}`);
    this.name = "FindingsResponseError";
  }
}

function isLonLat(value: unknown): value is [number, number] {
  return (
    Array.isArray(value) &&
    value.length >= 2 &&
    isFiniteNumber(value[0]) &&
    isFiniteNumber(value[1]) &&
    Math.abs(value[0]) <= 180 &&
    Math.abs(value[1]) <= 90
  );
}

function isLine(value: unknown): value is [number, number][] {
  return Array.isArray(value) && value.length >= 2 && value.every(isLonLat);
}

function isRing(value: unknown): value is [number, number][] {
  return Array.isArray(value) && value.length >= 4 && value.every(isLonLat);
}

function isRings(value: unknown): value is [number, number][][] {
  return Array.isArray(value) && value.length >= 1 && value.every(isRing);
}

/** The shape, if it is a line or an area the map can draw, or undefined. */
function parseShape(value: unknown): FindingShape | undefined {
  if (!isRecord(value)) return undefined;
  const { type, coordinates } = value;
  if (type === "LineString" && isLine(coordinates)) return { type, coordinates };
  if (type === "MultiLineString" && Array.isArray(coordinates) && coordinates.length > 0 && coordinates.every(isLine)) {
    return { type, coordinates: coordinates as [number, number][][] };
  }
  if (type === "Polygon" && isRings(coordinates)) return { type, coordinates };
  if (type === "MultiPolygon" && Array.isArray(coordinates) && coordinates.length > 0 && coordinates.every(isRings)) {
    return { type, coordinates: coordinates as [number, number][][][] };
  }
  return undefined;
}

/**
 * The feature, checked and trimmed to what the map uses, or null if it cannot
 * be drawn. `obscured` accepts true only, so anything else draws a point, and
 * the server is the one that must say a position is generalised.
 */
function parseFeature(value: unknown): FindingFeature | null {
  if (!isRecord(value) || !isRecord(value.geometry) || !isRecord(value.properties)) return null;
  const { geometry, properties } = value;
  if (geometry.type !== "Point" || !isLonLat(geometry.coordinates)) return null;
  const {
    public_id: publicId,
    tier,
    state,
    sensitivity,
    obscured,
    square,
    title,
    feature_class: featureClass,
    shape,
  } = properties;
  if (typeof publicId !== "string" || publicId === "" || typeof tier !== "string") return null;

  const parsed: FindingProperties = {
    public_id: publicId,
    tier,
    state: typeof state === "string" ? state : "open",
    obscured: obscured === true,
  };
  if (isSensitivity(sensitivity)) parsed.sensitivity = sensitivity;
  if (typeof square === "string") parsed.square = square;
  if (typeof title === "string") parsed.title = title;
  if (typeof featureClass === "string") parsed.feature_class = featureClass;
  // A square stands for an obscured finding, and its shape is never drawn, whatever was sent.
  const drawn = parsed.obscured ? undefined : parseShape(shape);
  if (drawn) parsed.shape = drawn;

  const feature: FindingFeature = {
    type: "Feature",
    geometry: { type: "Point", coordinates: [geometry.coordinates[0], geometry.coordinates[1]] },
    properties: parsed,
  };
  if (typeof value.id === "string" || typeof value.id === "number") feature.id = value.id;
  return feature;
}

/**
 * Check a response and return the findings that can be drawn. A document
 * that is not a feature collection is an error. A single feature the map
 * cannot draw is dropped, so one bad row never blanks the overlay.
 */
export function parseFindingCollection(value: unknown): FindingCollection {
  if (!isRecord(value) || value.type !== "FeatureCollection" || !Array.isArray(value.features)) {
    throw new FindingsResponseError("not a GeoJSON FeatureCollection");
  }
  const features: FindingFeature[] = [];
  for (const candidate of value.features) {
    const feature = parseFeature(candidate);
    if (feature) features.push(feature);
  }
  const nextCursor = typeof value.next_cursor === "string" ? value.next_cursor : null;
  return { type: "FeatureCollection", features, next_cursor: nextCursor };
}

/**
 * Check a page of `GET /findings` (JSON) before it is trusted. The list
 * shows every field it keeps, so a page whose items lack them is refused
 * whole, rather than drawn with holes.
 */
export function parseFindingPage(value: unknown): FindingPage {
  if (!isRecord(value) || !Array.isArray(value.items)) throw new FindingsResponseError("not a page of findings");
  for (const item of value.items) {
    const ok =
      isRecord(item) &&
      typeof item.public_id === "string" &&
      typeof item.title === "string" &&
      typeof item.tier === "string" &&
      typeof item.state === "string" &&
      typeof item.feature_class === "string" &&
      isRecord(item.location) &&
      isFiniteNumber(item.location.lon) &&
      isFiniteNumber(item.location.lat);
    if (!ok) throw new FindingsResponseError("a finding in the page is missing its title, tier, state or place");
  }
  const cursor = value.next_cursor;
  if (cursor !== undefined && cursor !== null && typeof cursor !== "string") {
    throw new FindingsResponseError('"next_cursor" is not text');
  }
  return value as unknown as FindingPage;
}
