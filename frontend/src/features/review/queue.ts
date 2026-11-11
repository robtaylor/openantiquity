/**
 * Which card comes next. The server orders the queue (findings one answer
 * from moving up first, nearby ones before far ones) and pages it by an
 * offset, so a card can move between pages as people answer
 * (docs/ARCHITECTURE.md, "Second looks"). The browser only steps past the
 * cards this person has already answered, skipped or kept as a draft, and
 * starts from the top again once before saying the queue is empty.
 */

import type { ReviewCard, ReviewCardPage } from "./types.js";

export type NextCard =
  | { kind: "card"; card: ReviewCard }
  /** Every card on this page has been passed: ask for the next. */
  | { kind: "page"; cursor: string }
  /** The last page is used up: ask for the first again, once, in case the queue moved. */
  | { kind: "restart" }
  | { kind: "empty" };

export function pickNext(
  page: Pick<ReviewCardPage, "items" | "next_cursor">,
  passed: ReadonlySet<string>,
  restarted: boolean,
): NextCard {
  const card = page.items.find((item) => !passed.has(item.public_id));
  if (card) return { kind: "card", card };
  if (page.next_cursor) return { kind: "page", cursor: page.next_cursor };
  return restarted ? { kind: "empty" } : { kind: "restart" };
}

/** Three decimal places of a degree is about a hundred metres. */
const NEAR_PRECISION = 1000;

/**
 * Where the person has been looking, as the queue's `lon` and `lat`: the
 * map's centre, rounded so that a small pan doesn't make a different queue.
 */
export function nearFrom(centre: { lng: number; lat: number }): [number, number] | null {
  const { lng, lat } = centre;
  if (!Number.isFinite(lng) || !Number.isFinite(lat) || Math.abs(lng) > 180 || Math.abs(lat) > 90) return null;
  return [Math.round(lng * NEAR_PRECISION) / NEAR_PRECISION, Math.round(lat * NEAR_PRECISION) / NEAR_PRECISION];
}
