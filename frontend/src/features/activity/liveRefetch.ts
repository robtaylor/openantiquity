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
 */

import type { QueryClient, QueryKey } from "@tanstack/react-query";
import { META_QUERY_KEY } from "../../api/useMeta.js";
import { accountKeys } from "../account/api.js";
import { refreshFindingLists } from "../finding/useFinding.js";
import { findingKeys } from "../findings/keys.js";
import { notificationKeys } from "../notifications/keys.js";
import { reviewKeys } from "../review/keys.js";
import type { StreamEvent } from "./api.js";
import { activityKeys } from "./keys.js";

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

/** Refetch one target's queries, keeping any request already on its way. */
export function refetchTarget(client: QueryClient, target: RefetchTarget): void {
  const keep = { cancelRefetch: false };
  switch (target.kind) {
    case "finding":
      void client.invalidateQueries({ queryKey: findingKeys.detail(target.publicId) }, keep);
      return;
    case "feed":
      void client.invalidateQueries({ queryKey: activityKeys.all }, keep);
      return;
    case "notifications":
      void client.invalidateQueries({ queryKey: notificationKeys.all }, keep);
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
