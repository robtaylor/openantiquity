/**
 * Moderation in words: what a reported or acted-on thing is, what a
 * moderator did, and when a report is due. Built only from what the server
 * sent. `/meta` has no words for these, so they are written here, typed
 * over every target and action kind.
 */

import type { Meta } from "../../api/meta.js";
import { labelOf } from "../finding/describe.js";
import { LEVEL_NAMES } from "../finding/Tools.js";
import { isSensitivity } from "../findings/types.js";
import { pointWords } from "../people/describe.js";
import { roleWords } from "../people/roles.js";
import type { Action, ActionKind, Report, Target, TargetKind } from "./api.js";

/** "a comment", for a sentence. */
export const KIND_WORDS: Record<TargetKind, string> = {
  finding: "a finding",
  comment: "a comment",
  evidence: "a piece of evidence",
  mention: "a mention",
  photo: "a photo",
  user: "a person",
  investigation: "an investigation",
};

/** "Comment", for a heading. */
export const KIND_TITLES: Record<TargetKind, string> = {
  finding: "Finding",
  comment: "Comment",
  evidence: "Evidence",
  mention: "Mention",
  photo: "Photo",
  user: "Person",
  investigation: "Investigation",
};

/** What a target is, in a phrase: "a comment on Ring ditch by the long barrow", "the person QuietBarrow42". */
export function targetPhrase(target: Target): string {
  if (target.kind === "user") return target.title ? `${target.title}` : "a person who has left";
  if (target.kind === "finding") return target.title ? `the finding “${target.title}”` : "a finding";
  if (target.kind === "investigation") return target.title ? `the investigation “${target.title}”` : "an investigation";
  const on = target.finding ? ` on “${target.finding.title}”` : "";
  return `${KIND_WORDS[target.kind]}${on}`;
}

/** Where a target is now, beside it: hidden, removed by its author, gone. */
export function targetState(target: Target): string | null {
  if (!target.exists) return "It no longer exists.";
  if (target.removed) return target.kind === "user" ? "They have deleted their account." : "Its author removed it.";
  if (target.hidden) return "Hidden by a moderator.";
  return null;
}

const VERBS: Record<ActionKind, string> = {
  hide: "hid",
  unhide: "showed again",
  resolve_report: "resolved a report on",
  change_role: "changed the role of",
  ban: "banned",
  unban: "lifted the ban on",
  change_sensitivity: "changed the level of",
  approve_photo: "approved",
  reject_photo: "refused",
};

function text(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

/**
 * A level's name as it reads inside a sentence. The log keeps what was stored
 * when the moderator acted, so a level this version has no name for is shown
 * as stored.
 */
function levelWord(level: string): string {
  return isSensitivity(level) ? LEVEL_NAMES[level].toLowerCase() : level.replaceAll("_", " ");
}

/** What changed, from the action's data: "from Member to Trusted member", "from protected to open". */
function change(action: Action): string | null {
  const from = text(action.data?.from);
  const to = text(action.data?.to);
  if (from === null || to === null) return null;
  if (action.action === "change_role") return `from ${roleWords(from).label} to ${roleWords(to).label}`;
  if (action.action === "change_sensitivity") return `from ${levelWord(from)} to ${levelWord(to)}`;
  return null;
}

/** One entry of the log in a sentence: "Ada Lovelace hid a comment on “Ring ditch”." */
export function actionSentence(action: Action): string {
  let verb = VERBS[action.action];
  if (action.action === "resolve_report") {
    const outcome = text(action.data?.outcome);
    verb = outcome === "upheld" ? "upheld a report on" : outcome === "dismissed" ? "dismissed a report on" : verb;
  }
  const detail = change(action);
  return `${action.actor.display_name} ${verb} ${targetPhrase(action.target)}${detail ? ` ${detail}` : ""}.`;
}

/** The reasons whose reports the law gives a deadline, from `/meta`. */
export function deadlineReasons(meta: Meta): string[] {
  return meta.vocab.report_reasons.filter((reason) => reason.due_hours !== null).map((reason) => reason.id);
}

export function reasonLabel(meta: Meta, reason: string): string {
  return labelOf(meta.vocab.report_reasons, reason);
}

const DUE = new Intl.DateTimeFormat("en-GB", {
  weekday: "short",
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

/** "Due by Fri 13 Nov, 14:00", or "Overdue since …" once that has passed. */
export function dueWords(report: Pick<Report, "due_at">, now: number = Date.now()): string | null {
  if (report.due_at === null) return null;
  const due = new Date(report.due_at);
  if (Number.isNaN(due.getTime())) return null;
  return due.getTime() < now ? `Overdue since ${DUE.format(due)}` : `Due by ${DUE.format(due)}`;
}

/**
 * The open reports in the order to read them: those with a legal deadline
 * first, soonest due first, then the rest oldest first, each report once.
 */
export function queueOrder(urgent: readonly Report[], rest: readonly Report[]): Report[] {
  const first = [...urgent]
    .filter((report) => report.due_at !== null)
    .sort((a, b) => (a.due_at ?? "").localeCompare(b.due_at ?? "") || a.id - b.id);
  const seen = new Set(first.map((report) => report.id));
  return [...first, ...rest.filter((report) => !seen.has(report.id))];
}

/** "A, B and C". */
function listWords(items: readonly string[]): string {
  if (items.length <= 1) return items.join("");
  return `${items.slice(0, -1).join(", ")} and ${items.at(-1)}`;
}

/**
 * Where one source of a member's points came from, for a moderator: the
 * steps their finding reached together in one sentence, then each other
 * reason. Said of them, not to them.
 */
export function pointSourceWords(meta: Meta, reasons: readonly string[]): string[] {
  // In the ladder's order, whatever order the server lists them in.
  const rank = (tier: string): number => {
    const at = meta.vocab.tiers.findIndex((known) => known.id === tier);
    return at === -1 ? meta.vocab.tiers.length : at;
  };
  const steps = reasons
    .flatMap((reason) => {
      const tier = /^tier_(.+)$/.exec(reason)?.[1];
      return tier === undefined ? [] : [tier];
    })
    .sort((a, b) => rank(a) - rank(b))
    .map((tier) => labelOf(meta.vocab.tiers, tier));
  const others = reasons
    .filter((reason) => !reason.startsWith("tier_"))
    .map((reason) => pointWords(meta, reason).replace(/^Your /, "Their "));
  return [...(steps.length > 0 ? [`Their finding reached ${listWords(steps)}`] : []), ...others];
}
