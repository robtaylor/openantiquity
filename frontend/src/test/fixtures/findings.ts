import type { FindingCollection, FindingFeature, Sensitivity } from "../../features/findings/types.js";
import { kmSquareAt } from "../../map/gridref.js";

/**
 * A stand-in for `GET /api/v1/findings?bbox=&format=geojson` around the
 * opening view at Avebury, as a signed-out visitor would receive it: open
 * findings exact, and protected and restricted ones generalised to the
 * centre of their one-kilometre square with `obscured` set, as Decision 0005
 * and the table in docs/ARCHITECTURE.md lay out. Used by unit tests, the
 * end-to-end stubs and the design screenshots.
 */

/** The centre of the fixture's opening view. */
export const FINDINGS_CENTRE = { lon: -1.8542, lat: 51.4286 };

/** A point this many metres east and north of `from`, near enough for laying out test points. */
export function offset(
  eastM: number,
  northM: number,
  from: { lon: number; lat: number } = FINDINGS_CENTRE,
): { lon: number; lat: number } {
  return {
    lon: from.lon + eastM / (111_320 * Math.cos((from.lat * Math.PI) / 180)),
    lat: from.lat + northM / 111_320,
  };
}

export interface FindingSpec {
  at: { lon: number; lat: number };
  public_id: string;
  tier: string;
  state?: string;
  sensitivity?: Sensitivity;
  /** True to send it generalised, as the server does for a viewer who may not see it exactly. */
  obscured?: boolean;
}

/** A finding as the server sends it. An obscured one is moved to the centre of its square and given its reference. */
export function findingFeature(spec: FindingSpec): FindingFeature {
  const { at, public_id: publicId, tier, state = "open", sensitivity = "open", obscured = false } = spec;
  if (!obscured) {
    return {
      type: "Feature",
      geometry: { type: "Point", coordinates: [at.lon, at.lat] },
      properties: { public_id: publicId, tier, state, sensitivity, obscured: false },
    };
  }
  const square = kmSquareAt(at.lon, at.lat);
  if (!square) throw new Error(`Fixture finding "${publicId}" is off the grid`);
  const corners = square.ring.slice(0, 4);
  const centre: [number, number] = [
    corners.reduce((sum, [lon]) => sum + lon, 0) / corners.length,
    corners.reduce((sum, [, lat]) => sum + lat, 0) / corners.length,
  ];
  return {
    type: "Feature",
    geometry: { type: "Point", coordinates: centre },
    properties: { public_id: publicId, tier, state, sensitivity, obscured: true, square: square.ref },
  };
}

export function findingCollection(specs: readonly FindingSpec[]): FindingCollection {
  return { type: "FeatureCollection", features: specs.map(findingFeature) };
}

const TIERS = ["spotted", "seen", "corroborated", "probable", "ground_checked", "confirmed"];

/** One finding per tier in a row, then known, ruled-out and disputed ones, then one protected and one restricted. */
export const FINDING_SPECS: readonly FindingSpec[] = [
  ...TIERS.map((tier, i) => ({ at: offset(-500 + i * 200, 300), public_id: `tier-${tier}`, tier })),
  { at: offset(-500, 100), public_id: "known-seen", tier: "seen", state: "known" },
  { at: offset(-300, 100), public_id: "known-probable", tier: "probable", state: "known" },
  { at: offset(-100, 100), public_id: "known-confirmed", tier: "confirmed", state: "known" },
  { at: offset(100, 100), public_id: "ruled-out", tier: "spotted", state: "ruled_out" },
  { at: offset(300, 100), public_id: "disputed", tier: "seen", state: "disputed" },
  // A round barrow defaults to protected. Signed out, it arrives as its square.
  { at: offset(-1400, -650), public_id: "protected", tier: "seen", sensitivity: "protected", obscured: true },
  { at: offset(1350, -480), public_id: "restricted", tier: "corroborated", sensitivity: "restricted", obscured: true },
];

export const findingsData: FindingCollection = findingCollection(FINDING_SPECS);
