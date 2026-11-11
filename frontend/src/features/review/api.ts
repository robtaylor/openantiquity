/**
 * The one request the blind queue makes before an answer: `GET
 * /review/next`. Its cards carry the place and the finder's view only, so
 * nothing about the finder's claim reaches the browser until the answer's
 * reply reveals it (Decision 0008). The answer itself goes through the
 * finding page's `putObservation`.
 */

import { apiFetch } from "../../api/client.js";
import type { ReviewCardPage } from "./types.js";

/** How many cards are asked for at a time. */
export const CARDS_PER_PAGE = 10;

export interface CardsRequest {
  /** Where the person has been looking, so nearby findings come first. */
  near: [number, number] | null;
  cursor: string | null;
}

export function fetchReviewCards({ near, cursor }: CardsRequest, signal?: AbortSignal): Promise<ReviewCardPage> {
  const query: Record<string, string | number> = { limit: CARDS_PER_PAGE };
  if (near) {
    query.lon = near[0];
    query.lat = near[1];
  }
  if (cursor) query.cursor = cursor;
  return apiFetch<ReviewCardPage>("/review/next", { query, signal });
}
