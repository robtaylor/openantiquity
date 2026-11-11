/**
 * Marking notifications read in the cached pages, ahead of the server, and
 * putting them back if it refuses. Pure, so the arithmetic of the unread
 * count is tested on its own.
 */

import type { InfiniteData } from "@tanstack/react-query";
import type { NotificationPage } from "./api.js";

export type NotificationPages = InfiniteData<NotificationPage, string | null>;

/** Which notifications to mark: these ids, or every one up to and including `upTo`. */
export type ReadChoice = { ids: readonly number[] } | { upTo: number };

function chosen(choice: ReadChoice, id: number): boolean {
  return "ids" in choice ? choice.ids.includes(id) : id <= choice.upTo;
}

function withCount(data: NotificationPages, change: number): NotificationPages {
  return {
    ...data,
    pages: data.pages.map((page, index) =>
      index === 0 ? { ...page, unread_count: Math.max(0, page.unread_count + change) } : page,
    ),
  };
}

/**
 * The pages with the chosen notifications marked read, and the ids that
 * were unread before, so a refusal can put exactly those back. The count
 * drops by the number marked here. Unread ones on pages not yet loaded,
 * which marking all reaches too, are left to the server's answer.
 */
export function markLocally(
  data: NotificationPages,
  choice: ReadChoice,
): { data: NotificationPages; changed: number[] } {
  const changed: number[] = [];
  const pages = data.pages.map((page) => ({
    ...page,
    items: page.items.map((item) => {
      if (item.read || !chosen(choice, item.id)) return item;
      changed.push(item.id);
      return { ...item, read: true };
    }),
  }));
  return { data: withCount({ ...data, pages }, -changed.length), changed };
}

/** The pages with these notifications unread again, after the server refused to mark them. */
export function unmarkLocally(data: NotificationPages, ids: readonly number[]): NotificationPages {
  let restored = 0;
  const pages = data.pages.map((page) => ({
    ...page,
    items: page.items.map((item) => {
      if (!item.read || !ids.includes(item.id)) return item;
      restored += 1;
      return { ...item, read: false };
    }),
  }));
  return withCount({ ...data, pages }, restored);
}

/** The pages with the unread count the server gave. */
export function withUnreadCount(data: NotificationPages, unread: number): NotificationPages {
  const first = data.pages[0];
  return first ? withCount(data, unread - first.unread_count) : data;
}
