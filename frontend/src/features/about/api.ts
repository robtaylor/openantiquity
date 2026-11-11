/**
 * What the about pages ask the API for beyond `/meta`: the sources the
 * browser queries itself, so each can be credited. The query keys are here,
 * under `["about"]`. The list is the same for everyone and changes only with
 * a release, so it is kept for the life of the page.
 */

import { apiFetch } from "../../api/client.js";
import type { components } from "../../api/schema.js";
import type { LiveSource } from "./creditList.js";

type LiveSources = components["schemas"]["LiveSources"];

export const aboutKeys = {
  all: ["about"] as const,
  liveSources: ["about", "live-sources"] as const,
};

export async function fetchLiveSources(signal?: AbortSignal): Promise<LiveSource[]> {
  const answer = await apiFetch<LiveSources>("/context/live-sources", { signal });
  return answer.items;
}
