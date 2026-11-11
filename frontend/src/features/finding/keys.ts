/**
 * Every query key a finding's page uses, in one place. A finding's own keys
 * sit under `findingKeys.detail(id)`, and so under `["findings"]`, so a save
 * anywhere that invalidates findings refreshes the page and all its parts.
 * Records don't depend on who is asking, but the suggestions for a finding
 * do, because they are measured from the position the viewer may see.
 */

import { findingKeys } from "../findings/keys.js";

export const findingPageKeys = {
  detail: findingKeys.detail,
  comments: (publicId: string) => [...findingKeys.detail(publicId), "comments"] as const,
  observations: (publicId: string) => [...findingKeys.detail(publicId), "observations"] as const,
  suggestions: (publicId: string) => [...findingKeys.detail(publicId), "suggested-records"] as const,
  /**
   * The follow-ups logged and the steps moved, for the timeline. `as` names the step and the follow-ups the page
   * holds, so a new entry or a move asks again.
   */
  ladderEvents: (publicId: string, as: string) => [...findingKeys.detail(publicId), "ladder-events", as] as const,
  /** The map and the Explore list, which a change to one finding can change too. */
  lists: [
    ["findings", "bbox"],
    ["findings", "list"],
  ] as const,
  recordSearch: (q: string) => ["records", "search", q] as const,
  record: (id: number) => ["records", "detail", id] as const,
};
