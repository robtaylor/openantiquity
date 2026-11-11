/**
 * Every query key for investigations, in one place, all under
 * `["investigations"]`. What the server sends depends on who is asking (a
 * private one is found only by its owner, and the findings in one come at
 * the position this viewer may see), so none of them is viewer-independent
 * and the session drops them all when the person changes.
 */

import type { Scope } from "./api.js";

export const investigationKeys = {
  all: ["investigations"] as const,
  lists: ["investigations", "list"] as const,
  /** One list: a scope, and for the public one the box it was narrowed to. */
  list: (scope: Scope, bbox: string | null) => ["investigations", "list", scope, bbox] as const,
  /** The person's own, read whole, for choosing one to add to. */
  mine: ["investigations", "list", "all-mine"] as const,
  detail: (publicId: string) => ["investigations", "detail", publicId] as const,
  items: (publicId: string) => ["investigations", "detail", publicId, "items"] as const,
  members: (publicId: string) => ["investigations", "detail", publicId, "members"] as const,
};
