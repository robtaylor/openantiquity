import type {
  FindingCollection,
  FindingCreate,
  FindingDetail,
  FindingFeature,
  FindingPage,
  FindingSummary,
  Sensitivity,
} from "../../features/findings/types.js";
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

/**
 * A finding as `GET /findings` lists it (the JSON page, not the map's
 * GeoJSON), from a map feature: the same place, tier and state, with the
 * rest filled in plainly. An obscured one keeps its square and has no
 * exact grid reference.
 */
export function findingSummary(feature: FindingFeature, overrides: Partial<FindingSummary> = {}): FindingSummary {
  const { properties } = feature;
  const [lon, lat] = feature.geometry.coordinates;
  return {
    public_id: properties.public_id,
    title: properties.title ?? `Finding ${properties.public_id}`,
    feature_class: (properties.feature_class ?? "enclosure") as FindingSummary["feature_class"],
    period: "unknown",
    tier: properties.tier as FindingSummary["tier"],
    state: properties.state as FindingSummary["state"],
    state_reason: null,
    confidence: 10,
    sensitivity: properties.sensitivity ?? "open",
    location: {
      lon,
      lat,
      obscured: properties.obscured,
      grid_ref: properties.obscured ? null : "SU 1025 6996",
      square: properties.obscured ? (properties.square ?? null) : null,
      outline: null,
    },
    author: { handle: "QuietBarrow42", display_name: "QuietBarrow42", role: "member" },
    created_at: "2026-11-01T10:00:00Z",
    updated_at: "2026-11-01T10:00:00Z",
    evidence_count: 0,
    comment_count: 0,
    mention_count: 0,
    ...overrides,
  };
}

/** A page of the list, as `GET /findings` sends it, holding `collection`'s findings. */
export function findingPage(collection: FindingCollection, nextCursor: string | null = null): FindingPage {
  return { items: collection.features.map((feature) => findingSummary(feature)), next_cursor: nextCursor };
}

/** What a signed-in member who isn't the finder may do on an open finding they see exactly. */
export const MEMBER_ACTIONS: FindingDetail["actions"] = {
  answer: { allowed: true, reason: null },
  add_evidence: { allowed: true, reason: null },
  comment: { allowed: true, reason: null },
  edit: { allowed: false, reason: "not_finder" },
  withdraw: { allowed: false, reason: "not_finder" },
  raise_level: { allowed: false, reason: "sensitivity_change_forbidden" },
  lower_level: { allowed: false, reason: "moderators_only" },
  verify: { allowed: false, reason: "verify_not_allowed" },
};

/** A finding's page, as `GET /findings/{id}` and `POST /findings` send it, built on a summary. */
export function findingDetail(summary: FindingSummary, overrides: Partial<FindingDetail> = {}): FindingDetail {
  return {
    ...summary,
    description: null,
    nation: "england",
    view_state: {},
    assessment: {
      tier: summary.tier,
      state: summary.state,
      state_reason: null,
      score: summary.confidence,
      next_tier: "seen",
      next_steps: [],
      tallies: null,
    },
    evidence: [],
    credits: [],
    answers_visible: true,
    my_observation: null,
    following: true,
    actions: MEMBER_ACTIONS,
    ...overrides,
  };
}

/**
 * What the server answers to `POST /findings` with this body: a new spotted
 * finding at the point sent, kept exact for its finder, titled after its
 * class when no title was sent.
 */
export function createdFinding(body: FindingCreate, publicId: string): FindingDetail {
  const [lon, lat] = (body.location.coordinates ?? []) as [number, number];
  const summary = findingSummary(
    {
      type: "Feature",
      geometry: { type: "Point", coordinates: [lon, lat] },
      properties: { public_id: publicId, tier: "spotted", state: "open", obscured: false },
    },
    {
      title: body.title ?? "Finding",
      feature_class: body.feature_class,
      period: body.period,
      sensitivity: body.sensitivity ?? "open",
    },
  );
  return findingDetail(summary, {
    description: body.description ?? null,
    view_state: body.view_state ?? {},
    location: { ...summary.location, outline: body.outline ?? null },
  });
}

/**
 * The features of `features` that `GET /findings` would answer `url` with:
 * inside its `bbox`, with its `tier`, `state` and `feature_class` filters
 * applied, and withdrawn findings left out unless asked for, as the server
 * does. A finding with no class counts as an enclosure, as `findingSummary` lists it.
 */
export function findingsMatching(features: readonly FindingFeature[], url: URL): FindingFeature[] {
  const box = (url.searchParams.get("bbox") ?? "").split(",").map(Number);
  const tiers = url.searchParams.getAll("tier");
  const states = url.searchParams.getAll("state");
  const classes = url.searchParams.getAll("feature_class");
  return features.filter((feature) => {
    if (box.length === 4 && box.every(Number.isFinite)) {
      const [west, south, east, north] = box as [number, number, number, number];
      const [lon, lat] = feature.geometry.coordinates;
      if (lon < west || lon > east || lat < south || lat > north) return false;
    }
    const { tier, state, feature_class: featureClass = "enclosure" } = feature.properties;
    if (tiers.length > 0 && !tiers.includes(tier)) return false;
    if (states.length > 0 ? !states.includes(state) : state === "withdrawn") return false;
    return classes.length === 0 || classes.includes(featureClass);
  });
}
