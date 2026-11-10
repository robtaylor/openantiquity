/**
 * Findings as the map receives them from `GET /findings?bbox=&format=geojson`.
 *
 * What a viewer is sent depends on who they are (Decision 0005), so the map
 * draws only what each feature says about itself. A feature with `obscured`
 * set stands for a finding whose exact position this viewer may not see. Its
 * point is the centre of a one-kilometre grid square and it has no outline.
 * Whether that happens is the server's decision. The shell never works it out
 * from the sensitivity level.
 */

import { isFiniteNumber, isRecord } from "../../api/guards.js";

/** How closely a finding's position is guarded. See docs/ARCHITECTURE.md, "Location sensitivity". */
export type Sensitivity = "open" | "protected" | "restricted";

export const SENSITIVITIES: readonly Sensitivity[] = ["open", "protected", "restricted"];

export function isSensitivity(value: unknown): value is Sensitivity {
  return (SENSITIVITIES as readonly unknown[]).includes(value);
}

export interface FindingProperties {
  public_id: string;
  tier: string;
  state: string;
  /** Absent when the server does not say, which the map treats as nothing more than unknown. */
  sensitivity?: Sensitivity;
  /** True when the point is the centre of a one-kilometre square, not the finding itself. */
  obscured: boolean;
  /** The grid reference of that square, such as "SU1069", when `obscured` is set. */
  square?: string;
  title?: string;
  feature_class?: string;
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
  return { type: "FeatureCollection", features };
}
