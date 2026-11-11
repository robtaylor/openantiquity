import { apiFetch } from "../../../api/client.js";
import type { ActivityPage } from "./followUps.js";

/** How many events the timeline reads: far more follow-ups and moves than any one finding has. */
const LADDER_EVENTS = 100;

/** A finding's follow-ups logged and steps moved, newest first, from the public feed. */
export function fetchLadderEvents(publicId: string, signal?: AbortSignal): Promise<ActivityPage> {
  return apiFetch<ActivityPage>("/activity", {
    query: { finding: publicId, kind: ["followup_logged", "tier_changed"], limit: LADDER_EVENTS },
    signal,
  });
}
