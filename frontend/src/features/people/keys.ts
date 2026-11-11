/**
 * Every query key a person's page uses, under `["people", handle]`. What a
 * profile lists depends on who is asking, so the session drops these when
 * the person changes.
 */

export const peopleKeys = {
  all: ["people"] as const,
  profile: (handle: string) => ["people", handle] as const,
  findings: (handle: string) => ["people", handle, "findings"] as const,
  contributions: (handle: string, kind: "second_look" | null) =>
    ["people", handle, "contributions", kind ?? "helped"] as const,
  points: (handle: string) => ["people", handle, "points"] as const,
};
