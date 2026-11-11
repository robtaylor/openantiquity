import type { Mention, MentionPreview, RecentMention } from "../../features/mentions/types.js";
import { OTHER, pageFixture, squareFixture } from "./findingPage.js";

/**
 * Mentions as the API sends them: on a finding's page, in a preview before
 * one is saved, and in the recent feed with their finding. Shared by the unit
 * tests, the end-to-end stubs and the design screenshots.
 */

/** A YouTube video that comes to the finding twelve minutes in, added by a member. */
export function mentionFixture(overrides: Partial<Mention> = {}): Mention {
  return {
    id: 1,
    kind: "video",
    url: "https://youtu.be/dQw4w9WgXcQ?t=754",
    canonical_url: "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    provider: "youtube",
    title: "Barrows of the Marlborough Downs",
    author_name: "Downland Walks",
    thumbnail_url: "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
    published_at: "2026-10-28T18:00:00Z",
    start_seconds: 754,
    note: "Walks up to the ring ditch and points out the gap on the east side.",
    auto_detected: false,
    added_by: OTHER,
    created_at: "2026-11-06T09:30:00Z",
    hidden: false,
    ...overrides,
  };
}

/** A paper found by its DOI, with no picture. */
export function paperMentionFixture(overrides: Partial<Mention> = {}): Mention {
  return mentionFixture({
    id: 2,
    kind: "paper",
    url: "doi:10.5284/1040209",
    canonical_url: "https://doi.org/10.5284/1040209",
    provider: "doi",
    title: "Prehistoric round barrows of north Wiltshire: a LIDAR survey",
    author_name: "Wiltshire Archaeological and Natural History Society",
    thumbnail_url: null,
    published_at: "2019-05-01T00:00:00Z",
    start_seconds: null,
    note: null,
    ...overrides,
  });
}

/** What the preview found for `mentionFixture`'s address. */
export function previewFixture(overrides: Partial<MentionPreview> = {}): MentionPreview {
  const mention = mentionFixture();
  return {
    url: mention.url,
    canonical_url: mention.canonical_url,
    kind: mention.kind,
    provider: "youtube",
    start_seconds: mention.start_seconds,
    fetch_status: "ok",
    title: mention.title,
    author_name: mention.author_name,
    thumbnail_url: mention.thumbnail_url,
    published_at: mention.published_at,
    ...overrides,
  };
}

/** A mention in the recent feed, on a finding the viewer sees exactly, or on one they see only as its square. */
export function recentMentionFixture(
  overrides: Partial<Mention> = {},
  options: { obscured?: boolean } = {},
): RecentMention {
  const finding = options.obscured ? squareFixture() : pageFixture();
  return {
    ...mentionFixture(overrides),
    finding: {
      public_id: finding.public_id,
      title: finding.title,
      feature_class: finding.feature_class,
      tier: finding.tier,
      state: finding.state,
      location: finding.location,
      author: finding.author,
    },
  };
}
