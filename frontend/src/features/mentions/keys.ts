/**
 * Every query key mentions use, in one place. A finding's mentions sit under
 * `findingKeys.detail(id)`, so whatever refreshes the finding refreshes them
 * too. The recent feed has its own key. Both depend on who is asking, since a
 * hidden mention is listed only for its adder and moderators, and positions
 * in titles are hidden from those who don't see the place, so the session
 * drops them when the person changes.
 */

import { findingKeys } from "../findings/keys.js";

export const mentionKeys = {
  forFinding: (publicId: string) => [...findingKeys.detail(publicId), "mentions"] as const,
  recent: ["mentions", "recent"] as const,
};
