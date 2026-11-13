/**
 * What happened, in a plain sentence, for the feed and for notifications.
 *
 * A sentence says only what the server sent. An event a second look caused
 * has no actor (Decision 0008), and neither has one by a deleted account or
 * one the system made, so those sentences name nobody and never guess who
 * or what it was. Steps, states, explanations and evidence kinds take their
 * words from `/meta`.
 */

import type { Meta } from "../../api/meta.js";
import { labelOf, lowerFirst } from "../finding/describe.js";
import type { ActivityDetails, ActivityFinding, ActivityKind, PublicUser } from "./api.js";

/** The facts a sentence is made from, which a feed item and a notification both carry. */
export interface EventFacts {
  kind: ActivityKind;
  actor: PublicUser | null;
  finding: ActivityFinding | null;
  /** The investigation's title, where the server sent one. A notification never does. */
  investigationTitle: string | null;
  details: ActivityDetails;
}

/** A piece of a sentence: words, or a name to set apart from them. */
export type Part = string | { person: string } | { finding: string } | { investigation: string };

const A_FINDING = "a finding";

function findingPart(event: EventFacts): Part {
  return event.finding ? { finding: event.finding.title } : A_FINDING;
}

function person(actor: PublicUser): Part {
  return { person: actor.display_name };
}

function evidenceLabel(meta: Meta, details: ActivityDetails): string | null {
  return details.evidence_kind ? labelOf(meta.vocab.evidence_kinds, details.evidence_kind) : null;
}

function tierSentence(meta: Meta, event: EventFacts): Part[] {
  const subject = findingPart(event);
  const { tier_from: from, tier_to: to } = event.details;
  if (!to) return [subject, " changed step"];
  const order = meta.vocab.tiers.map((tier) => tier.id);
  const up = from ? order.indexOf(to) > order.indexOf(from) : true;
  const label = labelOf(meta.vocab.tiers, to);
  if (!event.actor) return [subject, up ? ` moved up to ${label}` : ` went back to ${label}`];
  return up
    ? [subject, ` moved up to ${label}, with help from `, person(event.actor)]
    : [subject, ` went back to ${label}, after a change by `, person(event.actor)];
}

/** Why a finding was explained, in a few words, or null when the server gave no reason this build knows. */
function explainedWhy(meta: Meta, reason: ActivityDetails["state_reason"]): string | null {
  if (!reason) return null;
  const explanation = meta.vocab.explanations.find((entry) => entry.id === reason);
  if (explanation) return lowerFirst(explanation.label);
  if (reason === "not_visible") return "most people who looked couldn't see it";
  if (reason === "ground_check") return "nothing on the ground supports it";
  return null;
}

function stateSentence(meta: Meta, event: EventFacts): Part[] {
  const subject = findingPart(event);
  const { state_to: to, state_reason: reason } = event.details;
  if (!to) return [subject, " changed state"];
  const by: Part[] = event.actor ? [" by ", person(event.actor)] : [];
  if (to === "open") return [subject, " is open again", ...by];
  const why = to === "ruled_out" ? explainedWhy(meta, reason) : null;
  return [subject, ` is now marked “${labelOf(meta.vocab.states, to)}”${why ? ` (${why})` : ""}`, ...by];
}

/** Capitalised and with its full stop, so it reads as a sentence however it starts and ends. */
function finish(parts: Part[]): Part[] {
  const [first, ...rest] = parts;
  const head = typeof first === "string" ? first.charAt(0).toUpperCase() + first.slice(1) : first;
  return [...(head === undefined ? [] : [head]), ...rest, "."].filter((part) => part !== "");
}

/** The sentence for one event. */
export function describeEvent(meta: Meta, event: EventFacts): Part[] {
  return finish(sentenceFor(meta, event));
}

function sentenceFor(meta: Meta, event: EventFacts): Part[] {
  const { actor } = event;
  const finding = findingPart(event);
  switch (event.kind) {
    case "finding_created":
      return actor ? [person(actor), " marked ", finding] : [finding, " was marked"];
    case "tier_changed":
      return tierSentence(meta, event);
    case "state_changed":
      return stateSentence(meta, event);
    case "observation_added":
      // Never named (Decision 0008). Should a name ever come, it is still only what the server sent.
      return actor ? [person(actor), " took a second look at ", finding] : [finding, " had a second look"];
    case "evidence_added": {
      const label = evidenceLabel(meta, event.details);
      const what = label ? `: ${lowerFirst(label)}` : "";
      return actor ? [person(actor), " added evidence to ", finding, what] : ["Evidence was added to ", finding, what];
    }
    case "followup_logged": {
      const label = evidenceLabel(meta, event.details);
      const what = label ? `: ${lowerFirst(label)}` : "";
      return actor
        ? [person(actor), " logged a follow-up on ", finding, what]
        : ["A follow-up was logged on ", finding, what];
    }
    case "comment_added":
      return actor ? [person(actor), " commented on ", finding] : [finding, " has a new comment"];
    case "mention_added":
      return actor ? [person(actor), " added a mention of ", finding] : [finding, " was mentioned"];
    case "investigation_published": {
      const investigation: Part = event.investigationTitle
        ? { investigation: event.investigationTitle }
        : "an investigation";
      return actor ? [person(actor), " published ", investigation] : [investigation, " was published"];
    }
    case "shape_extended":
      return [finding, " was extended"];
    case "investigation_invitation":
      return actor
        ? [person(actor), " invited you to join an investigation"]
        : ["You've been invited to join an investigation"];
  }
}

/** The sentence as plain text, for a link's name or a test. */
export function sentenceText(parts: readonly Part[]): string {
  return parts
    .map((part) => {
      if (typeof part === "string") return part;
      if ("person" in part) return part.person;
      if ("finding" in part) return part.finding;
      return part.investigation;
    })
    .join("");
}
