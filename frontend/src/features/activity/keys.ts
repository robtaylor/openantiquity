/**
 * Every query key the activity feed uses, in one place, under `["activity"]`.
 * Each item's finding carries its position as the viewer may see it, so the
 * session drops these when the person changes, as it does every key but a few.
 */

import type { QueryKey } from "@tanstack/react-query";
import type { FeedRequest } from "./api.js";
import { isActivityKind } from "./kinds.js";

export const activityKeys = {
  all: ["activity"] as const,
  /** The feed's pages for a box (or everywhere) and the kinds asked for. */
  feed: (bbox: string | null, kinds: readonly string[]) => ["activity", "feed", bbox, kinds.join(",")] as const,
};

/** What a feed key asks for, read back from it, or null when it isn't a feed key. */
export function feedRequestOf(key: QueryKey): FeedRequest | null {
  const [head, part, bbox, kinds] = key;
  if (head !== "activity" || part !== "feed" || key.length !== 4) return null;
  if (bbox !== null && typeof bbox !== "string") return null;
  if (typeof kinds !== "string") return null;
  const list = kinds === "" ? [] : kinds.split(",");
  return list.every(isActivityKind) ? { bbox, kinds: list } : null;
}
