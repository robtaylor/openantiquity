/**
 * The requests a finding's page makes. Each is one endpoint from the API
 * table in docs/ARCHITECTURE.md, typed from the generated schema.
 */

import { API_BASE, ApiError, apiFetch } from "../../api/client.js";
import type { Sensitivity } from "../findings/types.js";
import type {
  AnswerHeld,
  Comment,
  CommentPage,
  EvidenceIn,
  FindingDetail,
  FindingUpdate,
  ObservationDetailIn,
  ObservationIn,
  ObservationPage,
  RecordOut,
  RecordPage,
  Reveal,
  ShapeSuggestion,
  SuggestionIn,
  Suggestions,
  Visible,
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

/** A moderator lowers a finding's level, with the reason the moderation log keeps. */
export function lowerSensitivity(publicId: string, level: Sensitivity, reason: string): Promise<FindingDetail> {
  return apiFetch<FindingDetail>(`/mod${findingUrl(publicId, "/sensitivity")}`, {
    method: "PUT",
    body: { level, reason },
  });
}

/**
 * Send a second look's answer alone, saying its detail follows (Decision
 * 0008), naming the shape revision it was given on (Decision 0029). It counts at once and the reply reveals nothing, unless the answer
 * was already revealed, as when another tab finished it: then the reply is
 * the reveal.
 */
export function giveAnswer(
  publicId: string,
  visible: Visible,
  shapeRevision: number | null = null,
): Promise<Reveal | AnswerHeld> {
  return putObservation(publicId, { visible, detail_follows: true, ...shapeRevisionField(shapeRevision) });
}

/**
 * The code the server refuses an answer with when the finding's shape has
 * changed since the revision the answer named: nothing is stored, and the
 * person is shown the finding again as it now is.
 */
export const SHAPE_CHANGED = "shape_changed";

/** What the page and the queue say when an answer was refused for a shape changed meanwhile. */
export const SHAPE_CHANGED_WORDS =
  "The finder changed its shape while you were looking, so your answer wasn't counted. Have a look at it as it is now.";

/** True for the refusal of an answer, or a save, made on a shape that has since changed. */
export function isShapeChanged(error: unknown): boolean {
  return error instanceof ApiError && error.code === SHAPE_CHANGED;
}

/** `shape_revision` for an answer's body, left out when it isn't known, as an old tab's answer is. */
export function shapeRevisionField(revision: number | null | undefined): { shape_revision?: number } {
  return revision === null || revision === undefined ? {} : { shape_revision: revision };
}

/** Add the detail to an answer given alone, or nothing to skip it. The reply is the reveal. */
export function revealAnswer(publicId: string, detail: ObservationDetailIn): Promise<Reveal> {
  return apiFetch<Reveal>(findingUrl(publicId, "/observation/reveal"), { method: "POST", body: detail });
}

/**
 * The reveal the person asked for on this screen. When the answer was
 * already revealed elsewhere with other detail, as from a second tab, the
 * server refuses the detail (`answer_final`) but still owes the comparison:
 * it is asked for again with nothing added, which answers with the reveal
 * as it stands, and `onFinal` says the detail wasn't added.
 */
export async function revealAsAsked(
  publicId: string,
  detail: ObservationDetailIn,
  onFinal: () => void,
): Promise<Reveal> {
  try {
    return await revealAnswer(publicId, detail);
  } catch (error) {
    if (!(error instanceof ApiError) || error.code !== "answer_final") throw error;
    const reveal = await revealAnswer(publicId, {});
    onFinal();
    return reveal;
  }
}

/**
 * Change a revealed answer's note, or count a taken-back answer again. The
 * answer itself is final. The reply reveals, unless the body says the detail
 * follows and the answer hasn't been revealed yet.
 */
export function putObservation(publicId: string, body: ObservationIn): Promise<Reveal | AnswerHeld> {
  return apiFetch<Reveal | AnswerHeld>(findingUrl(publicId, "/observation"), { method: "PUT", body });
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

/** Suggest a change to someone else's marking: the whole path, and the revision it was made on. */
export function suggestChange(publicId: string, body: SuggestionIn): Promise<ShapeSuggestion> {
  return apiFetch<ShapeSuggestion>(findingUrl(publicId, "/suggestions"), { method: "POST", body });
}

/** The suggester takes back a suggestion of their own that is still waiting. */
export function withdrawSuggestion(publicId: string, suggestionId: number): Promise<void> {
  return apiFetch<void>(findingUrl(publicId, `/suggestions/${suggestionId}`), { method: "DELETE" });
}

/** The keeper accepts a suggestion, naming the shape's revision they saw it against. */
export function acceptSuggestion(
  publicId: string,
  suggestionId: number,
  shapeRevision: number,
): Promise<FindingDetail> {
  return apiFetch<FindingDetail>(findingUrl(publicId, `/suggestions/${suggestionId}/accept`), {
    method: "POST",
    body: { shape_revision: shapeRevision },
  });
}

/** The keeper declines a suggestion. There is no reason to give: talk goes in the comments. */
export function declineSuggestion(publicId: string, suggestionId: number): Promise<ShapeSuggestion> {
  return apiFetch<ShapeSuggestion>(findingUrl(publicId, `/suggestions/${suggestionId}/decline`), { method: "POST" });
}

/** Offer the keeping of a marking to the member with this handle, replacing any offer standing. */
export function offerKeeping(publicId: string, handle: string): Promise<FindingDetail> {
  return apiFetch<FindingDetail>(findingUrl(publicId, "/keeping/offer"), { method: "PUT", body: { handle } });
}

/** Take back the standing offer, as its keeper, or turn it down, as the person offered. */
export function withdrawKeepingOffer(publicId: string): Promise<void> {
  return apiFetch<void>(findingUrl(publicId, "/keeping/offer"), { method: "DELETE" });
}

/** Take on the keeping offered to you. */
export function takeKeeping(publicId: string): Promise<FindingDetail> {
  return apiFetch<FindingDetail>(findingUrl(publicId, "/keeping/accept"), { method: "POST" });
}

/** The address that downloads one finding as GeoJSON or as a spreadsheet a records officer can use. */
export function exportUrl(publicId: string, format: "geojson" | "csv"): string {
  return `${API_BASE}${findingUrl(publicId, "/export")}?format=${format}`;
}
