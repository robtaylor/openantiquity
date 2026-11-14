import type {
  Comment,
  Evidence,
  FindingDetail,
  Observation,
  Reveal,
  ShapeSuggestion,
  SuggestedRecord,
  Suggestions,
} from "../../features/finding/types.js";
import { findingDetail, findingFeature, findingSummary, MEMBER_ACTIONS, offset } from "./findings.js";

/**
 * A finding's page as `GET /findings/{id}` sends it, for each tier, state
 * and viewer the page has to handle, with the evidence, comments, answers
 * and record suggestions that go with it. Shared by the unit tests, the
 * end-to-end stubs and the design screenshots.
 */

export const FINDER = { handle: "QuietBarrow42", display_name: "Ada Lovelace", role: "member" };
export const OTHER = { handle: "KeenLynchet7", display_name: "Mary Anning", role: "member" };
export const EXPERT = { handle: "DrDitch", display_name: "Dr Ditch", role: "expert" };

const AT = offset(0, 0);

/** A finding's page. Unless told otherwise: open, exact, seen by its finder's eyes only, with one step to go. */
export function pageFixture(overrides: Partial<FindingDetail> = {}): FindingDetail {
  const summary = findingSummary(
    {
      type: "Feature",
      geometry: { type: "Point", coordinates: [AT.lon, AT.lat] },
      properties: { public_id: "f-ring", tier: "spotted", state: "open", obscured: false },
    },
    {
      title: "Ring ditch by the long barrow",
      feature_class: "round_barrow",
      period: "bronze_age",
      sensitivity: "open",
      author: FINDER,
      confidence: 12,
    },
  );
  const base = findingDetail(summary, {
    description: "A faint ring with a gap on the east side, clearest with the light from the north-west.",
    view_state: { layer: "composite", zoom: 16.5, bearing: 12, pitch: 0, sun_azimuth: 315, sun_altitude: 25 },
    answers_visible: false,
    following: false,
    assessment: {
      tier: "spotted",
      state: "open",
      state_reason: null,
      score: 12,
      next_tier: "seen",
      next_steps: [{ code: "need_observers", prompt: "More people need to say whether they can see it." }],
      tallies: null,
    },
    credits: [{ user: FINDER, kind: "spotted" }],
  });
  const merged = { ...base, ...overrides };
  // The summary's tier and state are the assessment's.
  return { ...merged, tier: merged.assessment.tier, state: merged.assessment.state };
}

type Actions = FindingDetail["actions"];

/** What the finder may do on their own open finding, as the server says. */
export const FINDER_ACTIONS: Actions = {
  ...MEMBER_ACTIONS,
  answer: { allowed: false, reason: "own_finding" },
  edit: { allowed: true, reason: null },
  withdraw: { allowed: true, reason: null },
  raise_level: { allowed: true, reason: null },
  // The finder keeps it until it is handed on: they change it themselves, and decide what others suggest.
  suggest: { allowed: false, reason: "own_marking" },
  decide_suggestions: { allowed: true, reason: null },
  hand_on: { allowed: true, reason: null },
};

/** What a signed-out visitor may do: nothing until they sign in. */
export const SIGNED_OUT_ACTIONS: Actions = Object.fromEntries(
  Object.keys(MEMBER_ACTIONS).map((name) => [name, { allowed: false, reason: "unauthorised" }]),
) as Actions;

/** What a moderator who isn't the finder may do on an open finding. */
export const MODERATOR_ACTIONS: Actions = {
  ...MEMBER_ACTIONS,
  raise_level: { allowed: true, reason: null },
  lower_level: { allowed: true, reason: null },
};

/** The same finding as its finder sees it: answers visible, with the tallies. */
export function finderView(overrides: Partial<FindingDetail> = {}): FindingDetail {
  return pageFixture({
    answers_visible: true,
    following: true,
    actions: FINDER_ACTIONS,
    assessment: {
      ...pageFixture().assessment,
      next_steps: [{ code: "need_observers", prompt: "Two more people need to say they can see it.", people: 2 }],
      tallies: {
        observation_count: 0,
        seen: 0,
        unseen: 0,
        observers: 0,
        seen_ratio: null,
        class_support: { round_barrow: 1 },
        class_agreement: 1,
        community_class: null,
        explanations: {},
        checks: [],
      },
    },
    ...overrides,
  });
}

/** Seen by others, with two kinds of evidence still wanted. */
export function seenFixture(overrides: Partial<FindingDetail> = {}): FindingDetail {
  return pageFixture({
    confidence: 36,
    assessment: {
      tier: "seen",
      state: "open",
      state_reason: null,
      score: 36,
      next_tier: "corroborated",
      next_steps: [
        {
          code: "need_strand",
          prompt: "It needs two more kinds of evidence, such as an old map or an aerial photo.",
          strands_needed: 2,
          missing_strands: ["aerial", "historic_map", "records", "literature"],
        },
      ],
      tallies: null,
    },
    ...overrides,
  });
}

/** A finding shown as its square, at the square's centre, as a signed-out visitor gets a protected one. */
export function squareFixture(overrides: Partial<FindingDetail> = {}): FindingDetail {
  const base = pageFixture({ sensitivity: "protected", actions: SIGNED_OUT_ACTIONS });
  const square = findingFeature({ at: AT, public_id: base.public_id, tier: base.tier, obscured: true });
  const [lon, lat] = square.geometry.coordinates;
  return {
    ...base,
    location: {
      lon,
      lat,
      obscured: true,
      grid_ref: "SU 10 69",
      square: square.properties.square ?? null,
      outline: null,
      path: null,
      shape: { kind: null, length_m: null, revision: null, extent: null, changes: [], added_since_looked_m: null },
    },
    ...overrides,
  };
}

export function evidenceFixture(overrides: Partial<Evidence> = {}): Evidence {
  return {
    id: 1,
    kind: "historic_map",
    stance: "supports",
    title: "OS 6-inch, Wiltshire sheet XXVIII, 1888",
    note: "Drawn as a small circle with the word tumulus beside it.",
    url: "https://maps.example.org/view/1888/28",
    record_id: null,
    source_key: null,
    reference: null,
    relation: null,
    media_id: null,
    view: null,
    occurred_on: null,
    organisation: null,
    outcome: null,
    contributor: OTHER,
    created_at: "2026-11-02T09:00:00Z",
    verified_by: null,
    vote_total: 1,
    standing: true,
    independent: true,
    my_vote: null,
    redacted: false,
    endorsements: 1,
    disputes: 0,
    actions: { vote: { allowed: true, reason: null }, verify: { allowed: false, reason: "not_an_expert" } },
    ...overrides,
  };
}

export function observationFixture(overrides: Partial<Observation> = {}): Observation {
  return {
    user: OTHER,
    visible: "yes",
    feature_class: "round_barrow",
    period: null,
    explanation: null,
    not_modern: null,
    not_natural: null,
    not_artefact: null,
    note: null,
    created_at: "2026-11-03T12:00:00Z",
    updated_at: "2026-11-03T12:00:00Z",
    withdrawn: false,
    revealed: true,
    ...overrides,
  };
}

/** The page of someone whose answer is in and waits for its detail: nothing revealed yet. */
export function heldFixture(
  visible: Observation["visible"] = "yes",
  overrides: Partial<FindingDetail> = {},
): FindingDetail {
  return pageFixture({
    my_observation: observationFixture({ visible, feature_class: null, revealed: false }),
    actions: { ...MEMBER_ACTIONS, answer: { allowed: false, reason: "already_answered" } },
    ...overrides,
  });
}

/** What answering reveals: the finding with answers visible, and how this answer compares. */
export function revealFixture(
  answer: Observation,
  finding: FindingDetail = pageFixture(),
  overrides: Partial<Reveal> = {},
): Reveal {
  const after = {
    ...finding,
    answers_visible: true,
    my_observation: answer,
    following: true,
    assessment: { ...finding.assessment, next_steps: finding.assessment.next_steps },
  };
  return {
    revealed: true,
    observation: answer,
    finding: after,
    comparison: {
      finder_class: finding.feature_class,
      community_class: null,
      matches_finder: answer.feature_class === null ? null : answer.feature_class === finding.feature_class,
      others: { yes: 2, unsure: 1, no: 0 },
    },
    tier_before: finding.tier,
    tier_after: after.tier,
    state_before: finding.state,
    state_after: after.state,
    moved_up: false,
    ...overrides,
  };
}

export function commentFixture(overrides: Partial<Comment> = {}): Comment {
  return {
    id: 1,
    parent_id: null,
    author: OTHER,
    body: "There's a parch mark in the same place on the 2003 aerial.",
    created_at: "2026-11-02T10:00:00Z",
    edited_at: null,
    deleted: false,
    hidden: false,
    ...overrides,
  };
}

export function suggestionFixture(overrides: Partial<SuggestedRecord> = {}): SuggestedRecord {
  return {
    id: 501,
    source_key: "nhle-scheduled",
    name: "Bowl barrow 600m north of West Kennet",
    category: "designation",
    record_type: "scheduled monument",
    lon: AT.lon,
    lat: AT.lat,
    precision_m: null,
    url: "https://historicengland.org.uk/listing/the-list/list-entry/1008391",
    distance_m: 48,
    type_fit: true,
    score: 0.92,
    source: {
      key: "nhle-scheduled",
      name: "Scheduled monuments",
      publisher: "Historic England",
      licence: "Open Government Licence v3.0",
      licence_url: null,
      attribution: "© Historic England 2026",
      reuse: "open",
      licence_label: "OGL v3",
      credit: "© Historic England",
    },
    ...overrides,
  };
}

export function suggestionsFixture(items: SuggestedRecord[] = [suggestionFixture()]): Suggestions {
  return { origin: { lon: AT.lon, lat: AT.lat, obscured: false, square: null }, items };
}

const LINE_POINTS = [offset(-100, 0), offset(0, 20), offset(100, 0)];

/**
 * The finding's page for a line of three points at shape revision `revision`,
 * kept by its finder, as `actions` says. Pending suggestions go in
 * `suggestions`, as the server sends them to signed-in members.
 */
export function lineFixture(
  overrides: Partial<FindingDetail> = {},
  { revision = 3, suggestions = [] }: { revision?: number; suggestions?: ShapeSuggestion[] } = {},
): FindingDetail {
  const base = pageFixture();
  const coordinates = LINE_POINTS.map(({ lon, lat }) => [lon, lat]);
  return {
    ...base,
    location: {
      ...base.location,
      outline: { type: "LineString", coordinates },
      path: {
        closed: false,
        curve: "catmull-rom-centripetal-1",
        points: LINE_POINTS.map(({ lon, lat }) => ({ lon, lat, kind: "corner" as const })),
      },
      shape: {
        kind: "line",
        length_m: 205,
        revision,
        extent: [
          LINE_POINTS[0]?.lon ?? 0,
          LINE_POINTS[0]?.lat ?? 0,
          LINE_POINTS[2]?.lon ?? 0,
          LINE_POINTS[1]?.lat ?? 0,
        ],
        changes: [{ kind: "drawn", on: "2026-11-01" }],
        added_since_looked_m: null,
        suggestions,
      },
    },
    ...overrides,
  };
}

/** A pending suggestion that carries the line of `lineFixture` on 150 m to the east, made on revision 3 by `OTHER`. */
export function shapeSuggestionFixture(overrides: Partial<ShapeSuggestion> = {}): ShapeSuggestion {
  const points = [...LINE_POINTS, offset(250, 10)];
  return {
    id: 71,
    by: OTHER,
    created_at: "2026-11-10T09:30:00Z",
    base_revision: 3,
    behind: false,
    kind: "extended",
    length_m: 355,
    path: {
      closed: false,
      curve: "catmull-rom-centripetal-1",
      points: points.map(({ lon, lat }) => ({ lon, lat, kind: "corner" as const })),
    },
    outline: { type: "LineString", coordinates: points.map(({ lon, lat }) => [lon, lat]) },
    state: "pending",
    decided_at: null,
    ...overrides,
  };
}
