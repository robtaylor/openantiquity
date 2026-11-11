/**
 * What a live event asks the app to refetch, and how soon. An event is only
 * a hint: the queries it touches are invalidated, and those on screen ask
 * the ordinary routes again, which apply this viewer's rights. Queries not
 * on screen are only marked stale.
 *
 * Events come in bursts (a second look writes `observation_added` and a
 * `tier_changed` in the same moment), so each kind of refetch waits a
 * little and takes every event in that time at once: a finding's own page
 * hardly at all, so a tier change shows as it happens, and the map's
 * markers longest, because any finding anywhere can set them off.
 *
 * The feed and the notifications are lists a reader may have paged far
 * into. Refetching such a list would ask for every page again, so only its
 * first page is asked for, and what is new is put in front of what was
 * already there (`withNewestPage`).
 */

import type { InfiniteData, QueryClient, QueryKey } from "@tanstack/react-query";
import { META_QUERY_KEY } from "../../api/useMeta.js";
import { accountKeys } from "../account/api.js";
import { refreshFindingLists } from "../finding/useFinding.js";
import { findingKeys } from "../findings/keys.js";
import { fetchNotifications } from "../notifications/api.js";
import { notificationKeys } from "../notifications/keys.js";
import { reviewKeys } from "../review/keys.js";
import { fetchActivity, type StreamEvent } from "./api.js";
import { activityKeys, feedRequestOf } from "./keys.js";

export type RefetchTarget =
  | { kind: "finding"; publicId: string }
  | { kind: "feed" }
  | { kind: "notifications" }
  | { kind: "lists" };

/** How long each kind of refetch gathers events before it runs. */
export const REFETCH_DELAY_MS: Record<RefetchTarget["kind"], number> = {
  finding: 250,
  feed: 1_000,
  notifications: 2_000,
  lists: 5_000,
};

/** Kinds that can change how a finding is drawn on the map or listed in Explore. */
const MOVES_LISTS = new Set<StreamEvent["kind"]>(["finding_created", "tier_changed", "state_changed"]);

/**
 * The refetches one event asks for. `handle` is the signed-in person's, or
 * null when nobody is signed in: nobody is notified of their own action, so
 * their own events don't ask for their notifications.
 */
export function targetsFor(event: StreamEvent, handle: string | null): RefetchTarget[] {
  const targets: RefetchTarget[] = [{ kind: "feed" }];
  if (event.finding !== null) targets.push({ kind: "finding", publicId: event.finding });
  if (MOVES_LISTS.has(event.kind)) targets.push({ kind: "lists" });
  if (handle !== null && event.actor !== handle) targets.push({ kind: "notifications" });
  return targets;
}

export function targetKey(target: RefetchTarget): string {
  return target.kind === "finding" ? `finding:${target.publicId}` : target.kind;
}

/** Run each refetch once per gathering window, however many events ask for it in that time. */
export class Coalescer {
  private readonly timers = new Map<string, ReturnType<typeof setTimeout>>();

  schedule(key: string, delay: number, run: () => void): void {
    if (this.timers.has(key)) return;
    this.timers.set(
      key,
      setTimeout(() => {
        this.timers.delete(key);
        run();
      }, delay),
    );
  }

  cancelAll(): void {
    for (const timer of this.timers.values()) clearTimeout(timer);
    this.timers.clear();
  }
}

/** A page of a list newest first, as the feed and the notifications send them. */
interface NewestFirstPage {
  items: readonly { id: number }[];
  next_cursor?: string | null;
}

type Pages<P> = InfiniteData<P, string | null>;

/**
 * The pages with a fresh first page in front: everything new, then what the
 * first page held before, each item once and in its freshest form. The
 * first page keeps its old cursor, so the pages after it still follow on.
 */
export function withNewestPage<P extends NewestFirstPage>(data: Pages<P>, fresh: P): Pages<P> {
  const [first, ...rest] = data.pages;
  if (first === undefined) return { pages: [fresh], pageParams: [null] };
  const latest = new Set(fresh.items.map((item) => item.id));
  const kept = first.items.filter((item) => !latest.has(item.id));
  const seen = new Set([...latest, ...kept.map((item) => item.id)]);
  return {
    ...data,
    pages: [
      { ...fresh, items: [...fresh.items, ...kept], next_cursor: first.next_cursor },
      ...rest.map((page) => ({ ...page, items: page.items.filter((item) => !seen.has(item.id)) })),
    ],
  };
}

/**
 * Refetch the lists under `queryKey`. One that shows a single page is simply
 * refetched. One paged further, and on screen, has only its first page
 * asked for again (`fetchFirst`, or null when the key can't be read), with
 * what is new put in front. The rest are marked stale.
 */
export async function refreshNewest<P extends NewestFirstPage>(
  client: QueryClient,
  queryKey: QueryKey,
  fetchFirst: (key: QueryKey) => Promise<P> | null,
): Promise<void> {
  const keep = { cancelRefetch: false };
  await Promise.all(
    client
      .getQueryCache()
      .findAll({ queryKey })
      .map(async (query) => {
        const key = query.queryKey;
        const data = client.getQueryData<Pages<P>>(key);
        const asking = query.isActive() && data !== undefined && data.pages.length > 1 ? fetchFirst(key) : null;
        if (asking === null) {
          await client.invalidateQueries({ queryKey: key, exact: true }, keep);
          return;
        }
        try {
          const fresh = await asking;
          client.setQueryData<Pages<P>>(key, (current) => (current ? withNewestPage(current, fresh) : current));
        } catch {
          // The next event, or the next look at the list, asks again.
          await client.invalidateQueries({ queryKey: key, exact: true, refetchType: "none" });
        }
      }),
  );
}

/** Refetch one target's queries, keeping any request already on its way. */
export function refetchTarget(client: QueryClient, target: RefetchTarget): void {
  const keep = { cancelRefetch: false };
  switch (target.kind) {
    case "finding":
      void client.invalidateQueries({ queryKey: findingKeys.detail(target.publicId) }, keep);
      return;
    case "feed":
      void refreshNewest(client, activityKeys.all, (key) => {
        const request = feedRequestOf(key);
        return request ? fetchActivity(request, null) : null;
      });
      return;
    case "notifications":
      void refreshNewest(client, notificationKeys.all, () => fetchNotifications(null));
      return;
    case "lists":
      refreshFindingLists(client);
      return;
  }
}

/**
 * Whether a resync refetches this query. Not the vocabularies or who is
 * signed in, which events don't change, and not the blind queue, whose
 * cards are chosen once and must not shift under a reviewer.
 */
export function resyncs(queryKey: QueryKey): boolean {
  const [head] = queryKey;
  return head !== META_QUERY_KEY[0] && head !== accountKeys.me[0] && head !== reviewKeys.all[0];
}

/** Events may have been missed: refetch everything on screen that they could have changed. */
export function resync(client: QueryClient): void {
  void client.invalidateQueries({ predicate: (query) => resyncs(query.queryKey) }, { cancelRefetch: false });
}
