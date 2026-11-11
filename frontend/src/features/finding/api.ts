/**
 * The requests a finding's page makes. Each is one endpoint from the API
 * table in docs/ARCHITECTURE.md, typed from the generated schema.
 */

import { API_BASE, apiFetch } from "../../api/client.js";
import type { Sensitivity } from "../findings/types.js";
import type {
  Comment,
  CommentPage,
  EvidenceIn,
  FindingDetail,
  FindingUpdate,
  Media,
  ObservationIn,
  ObservationPage,
  RecordOut,
  RecordPage,
  Reveal,
  Suggestions,
} from "./types.js";

function findingUrl(publicId: string, rest = ""): string {
  return `/findings/${encodeURIComponent(publicId)}${rest}`;
}

export function fetchFinding(publicId: string, signal?: AbortSignal): Promise<FindingDetail> {
  return apiFetch<FindingDetail>(findingUrl(publicId), { signal });
}

export function updateFinding(publicId: string, body: FindingUpdate): Promise<FindingDetail> {
  return apiFetch<FindingDetail>(findingUrl(publicId), { method: "PATCH", body });
}

export function withdrawFinding(publicId: string): Promise<FindingDetail> {
  return apiFetch<FindingDetail>(findingUrl(publicId, "/withdraw"), { method: "POST" });
}

export function changeSensitivity(publicId: string, level: Sensitivity): Promise<FindingDetail> {
  return apiFetch<FindingDetail>(findingUrl(publicId, "/sensitivity"), { method: "PUT", body: { level } });
}

/** Give a second look, or change its note. The reply reveals the finding and everyone's answers. */
export function putObservation(publicId: string, body: ObservationIn): Promise<Reveal> {
  return apiFetch<Reveal>(findingUrl(publicId, "/observation"), { method: "PUT", body });
}

export function withdrawObservation(publicId: string): Promise<void> {
  return apiFetch<void>(findingUrl(publicId, "/observation"), { method: "DELETE" });
}

export function fetchObservations(publicId: string, signal?: AbortSignal): Promise<ObservationPage> {
  return apiFetch<ObservationPage>(findingUrl(publicId, "/observations"), { query: { limit: 100 }, signal });
}

export function addEvidence(publicId: string, body: EvidenceIn): Promise<FindingDetail> {
  return apiFetch<FindingDetail>(findingUrl(publicId, "/evidence"), { method: "POST", body });
}

/** Upload a photo. The answer's id goes with the evidence as `media_id`. */
export function uploadPhoto(file: Blob): Promise<Media> {
  return apiFetch<Media>("/media", { method: "POST", file });
}

/** Where a photo is served. Only people who may see it get it: others get 404. */
export function mediaUrl(mediaId: number): string {
  return `${API_BASE}/media/${mediaId}`;
}

export function deleteEvidence(evidenceId: number): Promise<void> {
  return apiFetch<void>(`/evidence/${evidenceId}`, { method: "DELETE" });
}

/** +1 endorses, -1 disputes, 0 takes the vote back. */
export function voteEvidence(evidenceId: number, value: -1 | 0 | 1): Promise<unknown> {
  return apiFetch<unknown>(`/evidence/${evidenceId}/vote`, { method: "PUT", body: { value } });
}

export function verifyEvidence(evidenceId: number): Promise<FindingDetail> {
  return apiFetch<FindingDetail>(`/evidence/${evidenceId}/verify`, { method: "POST" });
}

/** How many comments a page of the discussion holds. */
export const COMMENTS_PAGE_SIZE = 50;

export function fetchComments(publicId: string, cursor: string | null, signal?: AbortSignal): Promise<CommentPage> {
  return apiFetch<CommentPage>(findingUrl(publicId, "/comments"), {
    query: { limit: COMMENTS_PAGE_SIZE, cursor },
    signal,
  });
}

export function addComment(publicId: string, body: string, parentId: number | null): Promise<Comment> {
  return apiFetch<Comment>(findingUrl(publicId, "/comments"), {
    method: "POST",
    body: parentId === null ? { body } : { body, parent_id: parentId },
  });
}

export function deleteComment(commentId: number): Promise<void> {
  return apiFetch<void>(`/comments/${commentId}`, { method: "DELETE" });
}

export function setFollowing(publicId: string, following: boolean): Promise<unknown> {
  return apiFetch<unknown>(findingUrl(publicId, "/follow"), { method: following ? "PUT" : "DELETE" });
}

export function fetchSuggestedRecords(publicId: string, signal?: AbortSignal): Promise<Suggestions> {
  return apiFetch<Suggestions>(findingUrl(publicId, "/suggested-records"), { query: { limit: 5 }, signal });
}

export function searchRecords(q: string, signal?: AbortSignal): Promise<RecordPage> {
  return apiFetch<RecordPage>("/records/search", { query: { q, limit: 10 }, signal });
}

export function fetchRecord(recordId: number, signal?: AbortSignal): Promise<RecordOut> {
  return apiFetch<RecordOut>(`/records/${recordId}`, { signal });
}

/** The address that downloads one finding as GeoJSON or as a spreadsheet a records officer can use. */
export function exportUrl(publicId: string, format: "geojson" | "csv"): string {
  return `${API_BASE}${findingUrl(publicId, "/export")}?format=${format}`;
}
