/**
 * What a finding's page says, worked out from what the server sent. Nothing
 * here restates a rule of the confidence ladder: the next steps, the tier and
 * the state are the assessment's, and this file only puts them into words
 * and picks which form a step's button opens.
 */

import type { EvidenceKind, Meta } from "../../api/meta.js";
import type { Sensitivity } from "../findings/types.js";
import type { CreditKind, Evidence, FindingDetail, NextStep } from "./types.js";

export function labelOf(list: ReadonlyArray<{ id: string; label: string }>, id: string): string {
  return list.find((entry) => entry.id === id)?.label ?? id.replaceAll("_", " ");
}

/** "Old map" becomes "old map", but "LIDAR view" keeps its capitals. */
export function lowerFirst(text: string): string {
  const [first = "", second = ""] = text;
  return second === second.toUpperCase() && /\p{L}/u.test(second) ? text : first.toLowerCase() + text.slice(1);
}

const DATE = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });

/** "1 November 2026". */
export function formatDate(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : DATE.format(date);
}

/** "48 m away", "1.2 km away". */
export function distanceWords(metres: number): string {
  return metres < 1000 ? `${Math.round(metres)} m away` : `${(metres / 1000).toFixed(1)} km away`;
}

// --------------------------------------------------------------------------
// Who is looking
// --------------------------------------------------------------------------

// Known duplication of the server's rules, listed in docs/ARCHITECTURE.md
// ("A finding's page"): who may raise a level or verify, which steps a second
// look or an evidence group meets, and who sees what at each level. They go
// once `FindingDetail` says what this viewer may do and `/meta` says what
// meets each step.

/** Roles that may raise a finding's level as well as its finder (docs/ARCHITECTURE.md, "Location sensitivity"). */
const RAISING_ROLES = new Set(["trusted", "expert", "moderator", "admin"]);
/** Roles that may verify an official record. */
const VERIFYING_ROLES = new Set(["expert", "moderator", "admin"]);

export interface Viewer {
  /** Signed in and through the welcome step. */
  ready: boolean;
  signedIn: boolean;
  handle: string | null;
  role: string | null;
}

export interface ViewerPosition {
  isFinder: boolean;
  /** The server sent the exact place. Only then can this person answer, add evidence or vote. */
  seesExact: boolean;
  /** Withdrawn findings take no more work. */
  takesWork: boolean;
  /** Not the finder, sees it exactly, and hasn't answered: the inline second look is offered. */
  mayAnswer: boolean;
  hasAnswered: boolean;
  mayRaise: boolean;
  mayVerify: boolean;
}

export function positionOf(finding: FindingDetail, viewer: Viewer): ViewerPosition {
  const isFinder = viewer.handle !== null && viewer.handle === finding.author.handle;
  const seesExact = !finding.location.obscured;
  const takesWork = finding.state !== "withdrawn";
  const hasAnswered = finding.my_observation !== null;
  return {
    isFinder,
    seesExact,
    takesWork,
    mayAnswer: !isFinder && seesExact && takesWork && !hasAnswered,
    hasAnswered,
    mayRaise: takesWork && (isFinder || (viewer.role !== null && RAISING_ROLES.has(viewer.role))),
    mayVerify: viewer.role !== null && VERIFYING_ROLES.has(viewer.role),
  };
}

// --------------------------------------------------------------------------
// The head
// --------------------------------------------------------------------------

/**
 * Why a finding isn't open, in words. The reason codes that are explanations
 * take their label from `/meta`. `/meta` has no words for the other two yet,
 * so they are written here.
 */
export function stateReason(meta: Meta, finding: FindingDetail): string | null {
  const { state, state_reason: reason } = finding.assessment;
  if (state === "open") return null;
  if (state === "withdrawn") return "Its finder took it back. It stays on the map so nobody marks it again.";
  if (state === "ruled_out") {
    const explanation = meta.vocab.explanations.find((entry) => entry.id === reason);
    if (explanation) return `People agree it's most likely a ${lowerFirst(explanation.label)}. ${explanation.hint}`;
    if (reason === "not_visible") return "Most people who looked couldn't see it.";
    if (reason === "ground_check") return "Someone checked on the ground and found nothing to support it.";
  }
  return meta.vocab.states.find((entry) => entry.id === state)?.description ?? null;
}

/** Who sees the exact place at each level (Decision 0005). */
export function whoSees(level: Sensitivity): string {
  switch (level) {
    case "open":
      return "Everyone sees its exact place.";
    case "protected":
      return "Only people who have signed in see its exact place. Everyone else sees its one-kilometre square.";
    case "restricted":
      return "Only its finder, trusted members, archaeologists and moderators see its exact place. Everyone else sees its one-kilometre square.";
  }
}

/**
 * The one sentence for someone shown the square instead of the place: why,
 * and what would change it. Signing in shows a protected finding exactly.
 */
export function squareSentence(finding: FindingDetail, signedIn: boolean): string {
  const why = "Sites like this can attract illegal metal detecting, so its exact place is kept back.";
  if (finding.sensitivity === "protected" && !signedIn) return `${why} Sign in to see it.`;
  return `${why} Only its finder, trusted members, archaeologists and moderators see it.`;
}

// --------------------------------------------------------------------------
// Next steps
// --------------------------------------------------------------------------

/** What a next step's button does. */
export type StepAction =
  /** Give a second look, here on the page. */
  | { kind: "answer"; label: string }
  /** Open the form for one kind of evidence. */
  | { kind: "evidence"; evidenceKind: string; label: string }
  /** Go to evidence that is waiting to be endorsed or verified. */
  | { kind: "endorse"; evidenceIds: number[]; label: string }
  /** Ask other people: copy the page's link. */
  | { kind: "share"; label: string };

/** Steps that a second look meets. */
const ANSWER_CODES = new Set(["need_observers", "need_class_agreement", "need_check", "need_trusted_review"]);
/** Which group of evidence kinds in `/meta` meets each evidence step. */
const STEP_GROUPS: Record<string, string> = { need_ground: "field", need_official: "official" };

export function addLabel(kind: EvidenceKind): string {
  return `Add ${lowerFirst(kind.label)}`;
}

/**
 * The buttons for one next step, for this viewer. A second-look step offers
 * the answer to someone who may give one, and a link to share to the
 * finder, who can't. An evidence step offers a form for each kind that
 * would meet it: the missing strands' kinds, or the field or official
 * kinds. Evidence the step is waiting on can be gone to directly.
 */
export function stepActions(step: NextStep, meta: Meta, position: ViewerPosition): StepAction[] {
  if (!position.takesWork) return [];
  const actions: StepAction[] = [];
  if (ANSWER_CODES.has(step.code)) {
    if (position.mayAnswer) actions.push({ kind: "answer", label: "Give a second look" });
    else if (position.isFinder) actions.push({ kind: "share", label: "Copy a link to ask others" });
    return actions;
  }
  const pending = step.pending_evidence ?? [];
  if (pending.length > 0 && !position.isFinder) {
    actions.push({ kind: "endorse", evidenceIds: pending, label: pending.length === 1 ? "See it" : "See them" });
  }
  const group = STEP_GROUPS[step.code];
  const strands = new Set(step.missing_strands ?? []);
  const kinds = meta.vocab.evidence_kinds.filter((kind) =>
    group !== undefined ? kind.group === group : step.code === "need_strand" && strands.has(kind.strand),
  );
  for (const kind of kinds) actions.push({ kind: "evidence", evidenceKind: kind.id, label: addLabel(kind) });
  return actions;
}

/** What happened to a finding's step or state, in plain words, or null when nothing did. */
export function changeMessage(
  meta: Meta,
  before: { tier: string; state: string },
  after: { tier: string; state: string },
): string | null {
  const tier = meta.vocab.tiers.find((entry) => entry.id === after.tier);
  if (before.tier !== after.tier && tier) {
    const order = meta.vocab.tiers.map((entry) => entry.id);
    const up = order.indexOf(after.tier) > order.indexOf(before.tier);
    return `${up ? "It has moved up to" : "It has gone back to"} ${tier.label}. ${tier.description}`;
  }
  if (before.state !== after.state) {
    const state = meta.vocab.states.find((entry) => entry.id === after.state);
    if (after.state === "open") return "It's open again.";
    if (state) return `It's now marked ${lowerFirst(state.label)}. ${state.description}`;
  }
  return null;
}

// --------------------------------------------------------------------------
// Evidence and credit
// --------------------------------------------------------------------------

export interface EvidenceGroup {
  kind: EvidenceKind;
  items: Evidence[];
}

/** Evidence grouped by kind, in the vocabulary's order. A kind this build doesn't know goes last. */
export function groupEvidence(meta: Meta, evidence: readonly Evidence[]): EvidenceGroup[] {
  const known = meta.vocab.evidence_kinds;
  const groups: EvidenceGroup[] = [];
  for (const kind of known) {
    const items = evidence.filter((item) => item.kind === kind.id);
    if (items.length > 0) groups.push({ kind, items });
  }
  for (const item of evidence) {
    if (known.some((kind) => kind.id === item.kind)) continue;
    let group = groups.find((entry) => entry.kind.id === item.kind);
    if (!group) {
      group = { kind: { id: item.kind, label: item.kind, strand: "", group: "", hint: "" }, items: [] };
      groups.push(group);
    }
    group.items.push(item);
  }
  return groups;
}

/** Kinds of evidence an expert or moderator verifies before they count: the official ones. */
export function needsVerifying(meta: Meta, kindId: string): boolean {
  return meta.vocab.evidence_kinds.find((kind) => kind.id === kindId)?.group === "official";
}

const STANCE_WORDS: Record<string, string> = {
  supports: "Supports it",
  neutral: "Neither way",
  contradicts: "Counts against it",
};

export function stanceWords(stance: string): string {
  return STANCE_WORDS[stance] ?? stance;
}

const OUTCOME_WORDS: Record<string, string> = {
  supports: "Found it",
  inconclusive: "Couldn't tell",
  contradicts: "Found nothing there",
};

export function outcomeWords(outcome: string): string {
  return OUTCOME_WORDS[outcome] ?? outcome;
}

const CREDIT_WORDS: Record<CreditKind, string> = {
  spotted: "spotted it",
  saw_it: "can see it",
  could_not_see: "can't see it",
  unsure: "isn't sure",
  explained: "explained it",
  answered: "gave a second look",
  added_evidence: "added evidence",
  endorsed: "endorsed evidence",
  verified: "verified a record",
};

export function creditWords(kind: CreditKind): string {
  return CREDIT_WORDS[kind];
}
