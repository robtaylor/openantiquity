/**
 * The moderation routes: the report queue and resolving reports, hiding and
 * showing again, a finding's level, the members who could be made trusted,
 * roles, bans and the log. Every shape comes from the generated schema, and
 * every route needs a moderator through the welcome step
 * (docs/ARCHITECTURE.md, "Moderation"). The photo queue is in `photos/api.ts`.
 */

import { apiFetch } from "../../api/client.js";
import type { components } from "../../api/schema.js";
import type { FindingDetail, Sensitivity } from "../findings/types.js";

type Schemas = components["schemas"];

export type Report = Schemas["ReportOut"];
export type ReportPage = Schemas["Page_ReportOut_"];
export type Target = Schemas["TargetOut"];
export type TargetKind = Schemas["ReportTarget"];
export type Hidden = Schemas["Hidden"];
export type Eligible = Schemas["Eligible"];
export type EligiblePage = Schemas["Page_Eligible_"];
export type ModUser = Schemas["ModUser"];
export type Role = Schemas["Role"];
export type Ban = Schemas["Ban"];
export type Action = Schemas["Action"];
export type ActionPage = Schemas["Page_Action_"];
export type ActionKind = Schemas["ModerationActionKind"];
export type Resolved = Schemas["Resolved"];
export type ReportReasonId = Schemas["ReportReason"];
export type OrphanedMarking = Schemas["OrphanedMarking"];
export type OrphanedPage = Schemas["Page_OrphanedMarking_"];
export type EarlierShape = Schemas["EarlierShapeOut"];
export type EarlierShapePage = Schemas["Page_EarlierShapeOut_"];

/** How many reports, members or log entries a page holds. */
export const MOD_PAGE_SIZE = 20;

/** The path under `/mod` for each kind of thing a moderator can hide. A person is banned, not hidden. */
export const HIDE_PATHS: Record<Exclude<TargetKind, "user">, string> = {
  finding: "findings",
  comment: "comments",
  evidence: "evidence",
  mention: "mentions",
  photo: "media",
  investigation: "investigations",
};

export function isHideable(kind: TargetKind): kind is Exclude<TargetKind, "user"> {
  return kind !== "user";
}

/** `GET /mod/reports`: open reports, oldest first, optionally for one reason. */
export function fetchReports(
  {
    reason = null,
    cursor = null,
    limit = MOD_PAGE_SIZE,
  }: { reason?: string | null; cursor?: string | null; limit?: number },
  signal?: AbortSignal,
): Promise<ReportPage> {
  return apiFetch<ReportPage>("/mod/reports", { query: { status: "open", reason, cursor, limit }, signal });
}

export function resolveReport(reportId: number, outcome: "upheld" | "dismissed", note: string): Promise<Resolved> {
  return apiFetch<Resolved>(`/mod/reports/${reportId}/resolve`, { method: "POST", body: { outcome, note } });
}

/** Hide something, or show it again, with a reason for the log. `ref` is how the API names it (`Target.ref`). */
export function setHidden(
  kind: Exclude<TargetKind, "user">,
  ref: string,
  hidden: boolean,
  reason: string,
): Promise<Hidden> {
  return apiFetch<Hidden>(`/mod/${HIDE_PATHS[kind]}/${encodeURIComponent(ref)}/${hidden ? "hide" : "unhide"}`, {
    method: "POST",
    body: { reason },
  });
}

/** Set a finding's level, lower as well as higher, with a reason for the log. */
export function setLevel(publicId: string, level: Sensitivity, reason: string): Promise<FindingDetail> {
  return apiFetch<FindingDetail>(`/mod/findings/${encodeURIComponent(publicId)}/sensitivity`, {
    method: "PUT",
    body: { level, reason },
  });
}

export function fetchEligible(cursor: string | null, signal?: AbortSignal): Promise<EligiblePage> {
  return apiFetch<EligiblePage>("/mod/users/eligible", { query: { cursor, limit: MOD_PAGE_SIZE }, signal });
}

export function changeRole(handle: string, role: Role, reason: string): Promise<ModUser> {
  return apiFetch<ModUser>(`/mod/users/${encodeURIComponent(handle)}/role`, { method: "PUT", body: { role, reason } });
}

export function setBanned(handle: string, banned: boolean, reason: string): Promise<Ban> {
  return apiFetch<Ban>(`/mod/users/${encodeURIComponent(handle)}/${banned ? "ban" : "unban"}`, {
    method: "POST",
    body: { reason },
  });
}

/** `GET /mod/actions`: the log, newest first, for everything or for one target. */
export function fetchActions(
  { cursor = null, target = null }: { cursor?: string | null; target?: { kind: TargetKind; ref: string } | null },
  signal?: AbortSignal,
): Promise<ActionPage> {
  return apiFetch<ActionPage>("/mod/actions", {
    query: { cursor, limit: MOD_PAGE_SIZE, target_kind: target?.kind, target_id: target?.ref },
    signal,
  });
}

/** `GET /mod/markings/orphaned`: findings whose keeper's account is deleted or banned, newest first. Admins only. */
export function fetchOrphaned(cursor: string | null, signal?: AbortSignal): Promise<OrphanedPage> {
  return apiFetch<OrphanedPage>("/mod/markings/orphaned", { query: { cursor, limit: MOD_PAGE_SIZE }, signal });
}

/** `GET /mod/findings/{id}/shapes`: each change to the shape with the shape before it, newest first. Admins only. */
export function fetchEarlierShapes(
  publicId: string,
  cursor: string | null,
  signal?: AbortSignal,
): Promise<EarlierShapePage> {
  return apiFetch<EarlierShapePage>(`/mod/findings/${encodeURIComponent(publicId)}/shapes`, {
    query: { cursor },
    signal,
  });
}

/**
 * Put an orphaned marking back to the shape at `toRevision`, or take its
 * shape away with null, naming the revision the admin saw, with a reason for
 * the log.
 */
export function putMarking(
  publicId: string,
  toRevision: number | null,
  shapeRevision: number,
  reason: string,
): Promise<FindingDetail> {
  return apiFetch<FindingDetail>(`/mod/findings/${encodeURIComponent(publicId)}/marking`, {
    method: "PUT",
    body: { to_revision: toRevision, shape_revision: shapeRevision, reason },
  });
}
