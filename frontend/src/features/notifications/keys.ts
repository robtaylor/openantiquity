/**
 * Every query key notifications use, in one place, under `["notifications"]`.
 * They belong to one account, so the session drops them when the person changes.
 */

export const notificationKeys = {
  all: ["notifications"] as const,
  /** The pages of the list. The first carries the unread count, which the mode rail shows. */
  list: ["notifications", "list"] as const,
};
