/**
 * Reporting something to the moderators: `POST /reports`. A report names its
 * target as the API does, a finding or an investigation by public id, a
 * person by handle, anything else by id (docs/ARCHITECTURE.md, "Moderation").
 * The answer says only that it was received.
 */

import { apiFetch } from "../../api/client.js";
import type { components } from "../../api/schema.js";

type Schemas = components["schemas"];

export type ReportTargetKind = Schemas["ReportTarget"];
export type ReportReasonId = Schemas["ReportReason"];
export type ReportIn = Schemas["ReportIn"];
export type ReportCreated = Schemas["ReportCreated"];

/** Something that can be reported, named as the API names it. */
export interface ReportTarget {
  kind: ReportTargetKind;
  /** A public id for a finding or an investigation, a handle for a person, the id of anything else. */
  id: string | number;
}

export function sendReport(target: ReportTarget, reason: ReportReasonId, note: string | null): Promise<ReportCreated> {
  const body: ReportIn = { target_kind: target.kind, target_id: String(target.id), reason };
  if (note) body.note = note;
  return apiFetch<ReportCreated>("/reports", { method: "POST", body });
}
