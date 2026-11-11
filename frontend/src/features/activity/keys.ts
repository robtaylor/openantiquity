/**
 * Every query key the activity feed uses, in one place, under `["activity"]`.
 * Each item's finding carries its position as the viewer may see it, so the
 * session drops these when the person changes, as it does every key but a few.
 */

export const activityKeys = {
  all: ["activity"] as const,
  /** The feed's pages for a box (or everywhere) and the kinds asked for. */
  feed: (bbox: string | null, kinds: readonly string[]) => ["activity", "feed", bbox, kinds.join(",")] as const,
};
