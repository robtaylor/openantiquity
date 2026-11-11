import type { Action, Eligible, Report, Target } from "../../features/moderation/api.js";
import type { Contribution, Point, Profile } from "../../features/people/api.js";
import type { Media, QueuedMedia } from "../../features/photos/api.js";
import { FINDER, OTHER, pageFixture } from "./findingPage.js";

/**
 * People, reports, moderation and photos as the API sends them, for the
 * profile, report and moderation tests. Override any field.
 */

const RING = pageFixture();

/** A finding as a profile, a feed or a point names it. */
export const RING_REF = {
  public_id: RING.public_id,
  title: RING.title,
  feature_class: RING.feature_class,
  tier: RING.tier,
  state: RING.state,
  location: RING.location,
};

/** Someone else's page, as anyone sees it. */
export function profileFixture(overrides: Partial<Profile> = {}): Profile {
  return {
    handle: OTHER.handle,
    display_name: OTHER.display_name,
    avatar_url: null,
    role: "member",
    bio: "Walks the downs most weekends.",
    joined_at: "2026-10-02T09:00:00Z",
    reputation: 12,
    reputation_total: null,
    counts: { findings: 2, second_looks: null, evidence: 3, comments: 1, mentions: 0 },
    is_me: false,
    ...overrides,
  };
}

/** Someone aged 16 or 17, as the server sends them: their handle as their name, no picture and no bio. */
export function youngProfileFixture(overrides: Partial<Profile> = {}): Profile {
  return profileFixture({
    handle: "BrightCairn7",
    display_name: "BrightCairn7",
    avatar_url: null,
    bio: null,
    counts: { findings: 0, second_looks: null, evidence: 0, comments: 0, mentions: 0 },
    ...overrides,
  });
}

/** The person's own page, with the counts and totals only they get. */
export function ownProfileFixture(overrides: Partial<Profile> = {}): Profile {
  return profileFixture({
    handle: FINDER.handle,
    display_name: FINDER.display_name,
    reputation: 7,
    reputation_total: 8,
    counts: { findings: 1, second_looks: 2, evidence: 1, comments: 0, mentions: 0 },
    is_me: true,
    ...overrides,
  });
}

export function contributionFixture(overrides: Partial<Contribution> = {}): Contribution {
  return {
    kind: "evidence",
    id: 31,
    created_at: "2026-11-05T12:00:00Z",
    finding: RING_REF,
    subkind: "aerial",
    ...overrides,
  };
}

export function pointFixture(overrides: Partial<Point> = {}): Point {
  return {
    id: 5,
    delta: 2,
    reason: "tier_seen",
    created_at: "2026-11-06T12:00:00Z",
    finding: RING_REF,
    ...overrides,
  };
}

export function mediaFixture(overrides: Partial<Media> = {}): Media {
  return {
    id: 77,
    url: "/api/v1/media/77",
    content_type: "image/jpeg",
    width: 800,
    height: 600,
    bytes: 204_800,
    created_at: "2026-11-10T10:00:00Z",
    approved: false,
    rejected: false,
    hidden: false,
    ...overrides,
  };
}

export function queuedPhotoFixture(overrides: Partial<QueuedMedia> = {}): QueuedMedia {
  return { ...mediaFixture(), uploader: OTHER, findings: [RING.public_id], ...overrides };
}

export function targetFixture(overrides: Partial<Target> = {}): Target {
  return {
    kind: "comment",
    id: 501,
    ref: "501",
    exists: true,
    hidden: false,
    removed: false,
    finding: { public_id: RING.public_id, title: RING.title, hidden: false },
    owner: OTHER,
    title: null,
    body: "The farmer at Lower Barn says you can park in his yard.",
    url: null,
    photo_url: null,
    created_at: "2026-11-09T08:00:00Z",
    ...overrides,
  };
}

export function reportFixture(overrides: Partial<Report> = {}): Report {
  return {
    id: 1,
    created_at: "2026-11-10T09:00:00Z",
    reason: "privacy",
    note: "It names the farm and the farmer.",
    status: "open",
    reporter: { handle: "SharpEyedSam", display_name: "Sam Hill", avatar_url: null, role: "member" },
    target: targetFixture(),
    open_on_target: 1,
    due_at: null,
    resolved_by: null,
    resolved_at: null,
    ...overrides,
  };
}

export function eligibleFixture(overrides: Partial<Eligible> = {}): Eligible {
  return {
    user: {
      handle: OTHER.handle,
      display_name: OTHER.display_name,
      role: "member",
      avatar_url: null,
      reputation: 54,
      age_band: "18_plus",
      created_at: "2026-09-01T10:00:00Z",
      banned: false,
      banned_at: null,
    },
    sources: [
      {
        finding: { public_id: RING.public_id, title: RING.title, hidden: false },
        points: 27,
        reasons: ["tier_seen", "tier_ground_checked", "tier_corroborated"],
        others: [{ handle: "SharpEyedSam", display_name: "Sam Hill", avatar_url: null, role: "member" }],
      },
      { finding: null, points: 2, reasons: ["second_looks"], others: [] },
    ],
    associates: [
      {
        user: { handle: "SharpEyedSam", display_name: "Sam Hill", avatar_url: null, role: "member" },
        shared_findings: 1,
      },
    ],
    ...overrides,
  };
}

export function actionFixture(overrides: Partial<Action> = {}): Action {
  return {
    id: 9,
    created_at: "2026-11-10T11:00:00Z",
    actor: { handle: "ModMorag", display_name: "Morag Kerr", avatar_url: null, role: "moderator" },
    action: "hide",
    target: targetFixture({ hidden: true }),
    reason: "Names a private landowner.",
    data: null,
    ...overrides,
  };
}
