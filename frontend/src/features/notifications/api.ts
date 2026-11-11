/**
 * The signed-in person's notifications: `GET /notifications`, newest first
 * with how many are unread, and `POST /notifications/read`. A notification
 * carries the same facts as a feed item, and names nobody for what a second
 * look caused (Decision 0008). Marking read needs only a session, since it
 * stores nothing.
 */

import { apiFetch } from "../../api/client.js";
import type { components } from "../../api/schema.js";

type Schemas = components["schemas"];

export type Notification = Schemas["NotificationOut"];
export type NotificationPage = Schemas["NotificationPageOut"];
export type MarkRead = Schemas["MarkRead"];
export type MarkReadResult = Schemas["MarkReadOut"];

/** How many notifications are asked for at a time. */
export const NOTIFICATIONS_PAGE_SIZE = 20;
/** The most ids one request may mark read (`MAX_MARK_IDS` on the server). */
export const MAX_MARK_IDS = 200;

export function fetchNotifications(cursor: string | null, signal?: AbortSignal): Promise<NotificationPage> {
  return apiFetch<NotificationPage>("/notifications", {
    query: { limit: NOTIFICATIONS_PAGE_SIZE, cursor },
    signal,
  });
}

export function markRead(body: MarkRead): Promise<MarkReadResult> {
  return apiFetch<MarkReadResult>("/notifications/read", { method: "POST", body });
}
