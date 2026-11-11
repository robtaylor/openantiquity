/**
 * Every query key help wanted uses, in one place, under `["help"]`. The
 * tasks depend on who is asking (the blind ones leave out the person's own
 * findings and the ones they've answered, and places follow Decision 0005),
 * so the session drops these when the person changes.
 */

export const helpKeys = {
  all: ["help"] as const,
  /** Every group with its first page. */
  groups: ["help", "groups"] as const,
  /** One group's pages. */
  group: (code: string) => ["help", "group", code] as const,
};
