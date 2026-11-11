import { infiniteQueryOptions, useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { useLocation } from "react-router";
import { isTransient } from "../../api/client.js";
import { toast } from "../../ui/toastStore.js";
import { useSession } from "../account/session.js";
import { REVIEW_PATH } from "../review/ReviewLayer.js";
import { fetchNotifications, MAX_MARK_IDS, markRead } from "./api.js";
import { notificationKeys } from "./keys.js";
import { markLocally, type NotificationPages, type ReadChoice, unmarkLocally, withUnreadCount } from "./readState.js";

/**
 * How often the list is asked for again while the page is in view, live
 * events aside. An invitation to an investigation is a notification with no
 * event behind it, so this is how one arrives on a page left open.
 */
export const NOTIFICATIONS_REFRESH_MS = 10 * 60_000;

export function notificationsQuery(enabled: boolean) {
  return infiniteQueryOptions({
    queryKey: notificationKeys.list,
    queryFn: ({ pageParam, signal }) => fetchNotifications(pageParam, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor ?? null,
    enabled,
    staleTime: 60_000,
    refetchInterval: NOTIFICATIONS_REFRESH_MS,
    retry: (failureCount, error) => failureCount < 1 && isTransient(error),
  });
}

/** The signed-in person's notifications, a page at a time. Asks for nothing when nobody is signed in. */
export function useNotifications() {
  const { status } = useSession();
  return useInfiniteQuery(notificationsQuery(status === "signed-in"));
}

/**
 * How many are unread, or null when nobody is signed in or the count isn't
 * known. Never a count for a visitor. While the blind second-look queue is
 * open the list is neither kept nor asked for, by its timer, a live event or
 * a resync, because its items carry findings' titles and steps (Decision
 * 0008), so the count isn't shown until the queue closes.
 */
export function useUnreadCount(): number | null {
  const { status } = useSession();
  const reviewing = useLocation().pathname === REVIEW_PATH;
  const counting = status === "signed-in" && !reviewing;
  const query = useInfiniteQuery({
    ...notificationsQuery(counting),
    select: (data) => data.pages[0]?.unread_count ?? null,
  });
  return counting ? (query.data ?? null) : null;
}

/** "1 new notification", "3 new notifications". */
export function unreadWords(count: number): string {
  return count === 1 ? "1 new notification" : `${count} new notifications`;
}

/**
 * Mark notifications read: shown at once, sent to the server, and put back
 * with a toast if it refuses. Returns the ids it marked here.
 */
export function useMarkRead(): (choice: ReadChoice) => Promise<number[]> {
  const client = useQueryClient();
  return useCallback(
    async (choice: ReadChoice) => {
      const key = notificationKeys.list;
      const before = client.getQueryData<NotificationPages>(key);
      if (!before) return [];
      const { data, changed } = markLocally(before, choice);
      if ("ids" in choice && changed.length === 0) return [];
      // A request already on its way was asked before this, and would bring the old state back.
      await client.cancelQueries({ queryKey: key, exact: true });
      client.setQueryData(key, data);
      try {
        const bodies =
          "ids" in choice
            ? chunks(changed, MAX_MARK_IDS).map((ids) => ({ ids, all: false }))
            : [{ all: true, up_to: choice.upTo }];
        let unread: number | null = null;
        for (const body of bodies) unread = (await markRead(body)).unread_count;
        if (unread !== null) {
          const count = unread;
          client.setQueryData<NotificationPages>(key, (current) =>
            current ? withUnreadCount(current, count) : current,
          );
        }
        return changed;
      } catch {
        client.setQueryData<NotificationPages>(key, (current) => (current ? unmarkLocally(current, changed) : current));
        toast("Your notifications couldn't be marked as read. They'll stay new for now.", { kind: "error" });
        return [];
      }
    },
    [client],
  );
}

function chunks<T>(items: readonly T[], size: number): T[][] {
  const out: T[][] = [];
  for (let start = 0; start < items.length; start += size) out.push(items.slice(start, start + size));
  return out;
}
