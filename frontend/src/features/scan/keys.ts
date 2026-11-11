/**
 * Every query key "Scan a square" uses, in one place.
 *
 * The next square depends on who is asking (never one they have done), so
 * it is dropped with everything else when the person changes. Coverage is
 * the same for everyone. The person's own findings in the square sit under
 * `findingKeys.all`, so saving a finding asks for them again with the map
 * and the list.
 */

import { findingKeys } from "../findings/keys.js";

export const scanKeys = {
  all: ["squares"] as const,
  /** One request for the next square: each press asks afresh, so `ticket` tells them apart. */
  next: (ticket: number) => ["squares", "next", ticket] as const,
  allCoverage: ["squares", "coverage"] as const,
  /** Coverage for a snapped box, and the overlay's retry count. */
  coverage: (bbox: readonly number[], attempt: number) => ["squares", "coverage", bbox.join(","), attempt] as const,
  /**
   * The person's own findings in a square, which count towards scanning it,
   * and how many finding drafts this page has saved, so a saved draft is asked for.
   */
  ownFindings: (square: string, handle: string, savedDrafts: number) =>
    [...findingKeys.all, "in-square", square, handle, savedDrafts] as const,
};
