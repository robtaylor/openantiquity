/**
 * Every query key moderation uses, under `["moderation"]`. All of it depends
 * on who is asking, so the session drops it when the person changes.
 */

export const moderationKeys = {
  all: ["moderation"] as const,
  /** Open reports, all of them or for one reason. */
  reports: (reason: string | null) => ["moderation", "reports", reason] as const,
  reportsAll: ["moderation", "reports"] as const,
  photos: ["moderation", "photos"] as const,
  eligible: ["moderation", "eligible"] as const,
  /** The log, all of it or for one target. */
  actions: (target: { kind: string; ref: string } | null) =>
    ["moderation", "actions", target?.kind ?? null, target?.ref ?? null] as const,
  actionsAll: ["moderation", "actions"] as const,
  orphaned: ["moderation", "orphaned"] as const,
  /** One finding's earlier shapes, for an admin putting one back. */
  shapes: (publicId: string) => ["moderation", "shapes", publicId] as const,
};
