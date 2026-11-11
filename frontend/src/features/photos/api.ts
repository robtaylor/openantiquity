/**
 * Photos: uploading one (`POST /media`, the image as the request body), the
 * approval queue moderators and trusted members share (`GET /mod/media`),
 * and approving or refusing one. Every shape comes from the generated
 * schema. A photo is only ever shown from the address the API gives for it
 * (docs/ARCHITECTURE.md, "Photos").
 */

import { API_BASE, apiFetch, apiUpload } from "../../api/client.js";
import type { components } from "../../api/schema.js";

type Schemas = components["schemas"];

export type Media = Schemas["MediaOut"];
export type QueuedMedia = Schemas["QueuedMediaOut"];
export type PhotoQueuePage = Schemas["Page_QueuedMediaOut_"];

/** How many waiting photos the queue asks for at a time. */
export const PHOTO_QUEUE_PAGE_SIZE = 20;

/**
 * Where a piece of evidence's photo is served. Evidence carries only the
 * photo's id, so this is the same address `MediaOut.url` gives for it.
 * Someone who may not see the photo is answered 404.
 */
export function photoAddress(mediaId: number): string {
  return `${API_BASE}/media/${mediaId}`;
}

/** Upload a photo, saying how much has gone as it goes. The answer's id goes with the evidence as `media_id`. */
export function uploadPhoto(
  file: Blob,
  options: { onProgress?: (fraction: number) => void; signal?: AbortSignal } = {},
): Promise<Media> {
  return apiUpload<Media>("/media", file, options);
}

/** `GET /mod/media`: photos waiting for approval, oldest first, without the viewer's own. */
export function fetchPhotoQueue(cursor: string | null, signal?: AbortSignal): Promise<PhotoQueuePage> {
  return apiFetch<PhotoQueuePage>("/mod/media", { query: { limit: PHOTO_QUEUE_PAGE_SIZE, cursor }, signal });
}

export function approvePhoto(mediaId: number): Promise<Media> {
  return apiFetch<Media>(`/mod/media/${mediaId}/approve`, { method: "POST" });
}

export function refusePhoto(mediaId: number, reason: string): Promise<Media> {
  return apiFetch<Media>(`/mod/media/${mediaId}/reject`, { method: "POST", body: { reason } });
}
