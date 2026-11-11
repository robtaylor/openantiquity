/**
 * The mention routes from the API table in docs/ARCHITECTURE.md, typed from
 * the generated schema.
 */

import { apiFetch } from "../../api/client.js";
import type { Mention, MentionIn, MentionPage, MentionPreview, RecentMentionPage } from "./types.js";

/** How many mentions a page holds, on a finding and in the recent feed. */
export const MENTIONS_PAGE_SIZE = 20;

export function fetchMentions(publicId: string, cursor: string | null, signal?: AbortSignal): Promise<MentionPage> {
  return apiFetch<MentionPage>(`/findings/${encodeURIComponent(publicId)}/mentions`, {
    query: { limit: MENTIONS_PAGE_SIZE, cursor },
    signal,
  });
}

/** What a mention of `url` would show. Nothing is saved, and a fetch that fails isn't an error. */
export function previewMention(url: string): Promise<MentionPreview> {
  return apiFetch<MentionPreview>("/mentions/preview", { method: "POST", body: { url } });
}

export function addMention(publicId: string, body: MentionIn): Promise<Mention> {
  return apiFetch<Mention>(`/findings/${encodeURIComponent(publicId)}/mentions`, { method: "POST", body });
}

/** Only the person who added a mention can remove it. */
export function deleteMention(mentionId: number): Promise<void> {
  return apiFetch<void>(`/mentions/${mentionId}`, { method: "DELETE" });
}

export function fetchRecentMentions(cursor: string | null, signal?: AbortSignal): Promise<RecentMentionPage> {
  return apiFetch<RecentMentionPage>("/mentions/recent", { query: { limit: MENTIONS_PAGE_SIZE, cursor }, signal });
}
