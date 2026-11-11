/**
 * The activity feed's requests and shapes: `GET /activity`, newest first,
 * and the event the live stream sends. Every shape comes from the generated
 * schema. An item's finding carries its position as this viewer may see it
 * (Decision 0005), and an event a second look caused names nobody
 * (Decision 0008), so the feed shows what each item says and nothing more.
 */

import { apiFetch } from "../../api/client.js";
import type { components } from "../../api/schema.js";

type Schemas = components["schemas"];

export type ActivityItem = Schemas["ActivityOut"];
export type ActivityPage = Schemas["Page_ActivityOut_"];
export type ActivityKind = Schemas["ActivityKind"];
export type ActivityFinding = Schemas["ActivityFinding"];
export type ActivityDetails = Schemas["ActivityDetails"];
export type PublicUser = Schemas["PublicUser"];
/** One live event: ids and a kind, a hint to ask the API again, never something to show. */
export type StreamEvent = Schemas["StreamEvent"];

export const ACTIVITY_API_PATH = "/activity";
/** How many items the feed asks for at a time. */
export const ACTIVITY_PAGE_SIZE = 30;

export interface FeedRequest {
  /** A `bboxParam` box, or null for everywhere. */
  bbox: string | null;
  /** The kinds asked for. Empty asks for every kind. */
  kinds: readonly ActivityKind[];
}

/** `GET /activity`: one page of what has happened, newest first. */
export function fetchActivity(
  request: FeedRequest,
  cursor: string | null,
  signal?: AbortSignal,
  limit = ACTIVITY_PAGE_SIZE,
): Promise<ActivityPage> {
  return apiFetch<ActivityPage>(ACTIVITY_API_PATH, {
    query: { bbox: request.bbox, kind: request.kinds, limit, cursor },
    signal,
  });
}

/** The newest item's id anywhere, or null when nothing has happened. How the app checks for news without a stream. */
export async function fetchLatestActivityId(signal?: AbortSignal): Promise<number | null> {
  const page = await fetchActivity({ bbox: null, kinds: [] }, null, signal, 1);
  return page.items[0]?.id ?? null;
}
