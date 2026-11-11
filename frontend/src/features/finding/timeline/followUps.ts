/**
 * The follow-up timeline: what happened on the ground and on record, drawn
 * from the evidence the finding's page already has. It is a second view of
 * that evidence, not a store of its own.
 *
 * Which kinds are follow-ups mirrors the backend, which logs every kind in
 * the field and official groups of `/meta`'s evidence kinds as
 * `followup_logged` (`FIELD_KINDS | OFFICIAL_KINDS` in services/findings.py).
 */

import type { EvidenceKind, Meta } from "../../../api/meta.js";
import type { components } from "../../../api/schema.js";
import type { Evidence } from "../types.js";

export type ActivityEvent = components["schemas"]["ActivityOut"];
export type ActivityPage = components["schemas"]["Page_ActivityOut_"];

/** The evidence groups whose kinds are follow-ups: work at the site, and the official record. */
const FOLLOW_UP_GROUPS = new Set(["field", "official"]);

/** The kinds of evidence that are follow-ups, in the vocabulary's order. */
export function followUpKinds(meta: Meta): EvidenceKind[] {
  return meta.vocab.evidence_kinds.filter((kind) => FOLLOW_UP_GROUPS.has(kind.group));
}

/** The day a follow-up happened: when it says it did, or else the day it was added. */
export function entryDay(item: Pick<Evidence, "occurred_on" | "created_at">): string {
  return item.occurred_on ?? item.created_at.slice(0, 10);
}

/** The follow-ups among the evidence, in date order, oldest first. Ties keep the order they were added in. */
export function timelineEntries(meta: Meta, evidence: readonly Evidence[]): Evidence[] {
  const kinds = new Set(followUpKinds(meta).map((kind) => kind.id));
  return evidence
    .filter((item) => kinds.has(item.kind))
    .sort((a, b) => entryDay(a).localeCompare(entryDay(b)) || a.created_at.localeCompare(b.created_at) || a.id - b.id);
}

/**
 * How long after a follow-up was logged the step it moved can be recorded.
 * Both are written in the same request, so they share a moment; this only
 * allows for clocks.
 */
const SAME_REQUEST_MS = 60_000;

/**
 * Which follow-ups moved the finding up the ladder, and to which step, from
 * the finding's `followup_logged` and `tier_changed` events. A step is put
 * down to a follow-up only when it was the very next of these events, by the
 * same person, at the same moment, because the server reassesses a finding in
 * the request that adds its evidence. A move that came later, such as when an
 * expert verified a record, is left unattributed.
 */
export function ladderMoves(meta: Meta, events: readonly ActivityEvent[]): Map<number, string> {
  const order = meta.vocab.tiers.map((tier) => tier.id);
  const moves = new Map<number, string>();
  let logged: ActivityEvent | null = null;
  for (const event of [...events].sort((a, b) => a.id - b.id)) {
    if (event.kind === "followup_logged") {
      logged = event;
      continue;
    }
    if (event.kind !== "tier_changed") continue;
    const { tier_from: from, tier_to: to } = event.details;
    const evidenceId = logged?.details.evidence_id;
    if (
      logged !== null &&
      evidenceId != null &&
      from != null &&
      to != null &&
      order.indexOf(to) > order.indexOf(from) &&
      // Both by someone named: a step recorded with no actor, as an answer's is, is never put down to a follow-up.
      logged.actor != null &&
      event.actor != null &&
      logged.actor.handle === event.actor.handle &&
      Math.abs(Date.parse(event.created_at) - Date.parse(logged.created_at)) <= SAME_REQUEST_MS
    ) {
      moves.set(evidenceId, to);
    }
    logged = null;
  }
  return moves;
}
