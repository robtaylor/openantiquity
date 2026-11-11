/**
 * Every query key the blind queue uses, in one place, all under
 * `["review"]`. The queue depends on who is asking (it leaves out a
 * person's own findings and the ones they have answered), so the session
 * drops these when the person changes, as it does every key but a few.
 */

export const reviewKeys = {
  all: ["review"] as const,
  /** One page of cards, for where the queue was started and the page's cursor. */
  cards: (near: [number, number] | null, cursor: string | null) =>
    ["review", "next", near?.join(",") ?? null, cursor] as const,
};
