/**
 * What a finding's page says, worked out from what the server sent. Nothing
 * here restates a rule of the confidence ladder: the next steps, the tier and
 * the state are the assessment's, and this file only puts them into words
 * and picks which form a step's button opens.
 */

import type { EvidenceKind, Meta, NextStepRule } from "../../api/meta.js";
import type { Sensitivity } from "../findings/types.js";
import type { ActionOut, CreditKind, Evidence, FindingDetail, NextStep } from "./types.js";

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

export interface Viewer {
  /** Signed in and through the welcome step. */
  ready: boolean;
  signedIn: boolean;
  handle: string | null;
  /** Only for drawing what this person adds before the server answers. What they may do is the server's to say. */
  role: string | null;
}

/**
 * The reasons a route gives someone who would be let through once they sign
 * in or finish the welcome step. Signed-out work is a draft, and a signed-in
 * press asks for the missing step first, so these still offer the action.
 */
const AFTER_SIGN_IN = new Set(["unauthorised", "onboarding_required"]);

/** Whether to offer an action the server rules on: allowed now, or once the person has signed in. */
export function offered(action: ActionOut): boolean {
  return action.allowed || (action.reason !== null && AFTER_SIGN_IN.has(action.reason));
}

export interface ViewerPosition {
  /** Only for the words the page uses, such as "Your finding". */
  isFinder: boolean;
  /** The server sent the exact place. */
  seesExact: boolean;
  /** Withdrawn findings take no more work. */
  takesWork: boolean;
  /** The inline second look is offered: the server allows an answer, or will once they sign in. */
  mayAnswer: boolean;
  hasAnswered: boolean;
  /** Their answer is in and counts, and waits for its detail or the reveal (Decision 0008). */
  answerHeld: boolean;
  mayAddEvidence: boolean;
  mayComment: boolean;
  mayEdit: boolean;
  mayWithdraw: boolean;
  mayRaise: boolean;
  /** A moderator may lower it, through the moderation route. */
  mayLower: boolean;
  mayVerify: boolean;
}

/**
 * What this viewer may do, from the finding's `actions`, which the server
 * works out by running the checks each route runs. The client adds nothing
 * to them but this: a signed-out visitor is told `unauthorised` for
 * everything, so for them the page offers only what the finding itself
 * allows, an exact place and a finding that isn't withdrawn.
 */
export function positionOf(finding: FindingDetail, viewer: Viewer): ViewerPosition {
  const { actions } = finding;
  const isFinder = viewer.handle !== null && viewer.handle === finding.author.handle;
  const seesExact = !finding.location.obscured;
  const takesWork = finding.state !== "withdrawn";
  const observation = finding.my_observation;
  const hasAnswered = observation !== null;
  /** Work that needs the exact place and an open finding: possible now, or once they sign in. */
  const onTheGround = (action: ActionOut) => offered(action) && seesExact && takesWork;
  return {
    isFinder,
    seesExact,
    takesWork,
    mayAnswer: !hasAnswered && onTheGround(actions.answer),
    hasAnswered,
    answerHeld: observation !== null && !observation.revealed && !observation.withdrawn,
    mayAddEvidence: onTheGround(actions.add_evidence),
    mayComment: offered(actions.comment),
    mayEdit: actions.edit.allowed,
    mayWithdraw: actions.withdraw.allowed,
    mayRaise: actions.raise_level.allowed,
    mayLower: actions.lower_level.allowed,
    mayVerify: actions.verify.allowed,
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

/**
 * Who sees the exact place at each level (Decision 0005), in the words of
 * `vocab.SENSITIVITY_LEVELS`. The download sentence is what a trusted member
 * or an archaeologist gets of a protected finding that a member doesn't.
 */
export function whoSees(level: Sensitivity): string {
  switch (level) {
    case "open":
      return "Everyone sees its exact place.";
    case "protected":
      return "Only people who have signed in see its exact place. Everyone else sees its one-kilometre square. Downloads give its exact place only to its finder, trusted members, archaeologists and moderators.";
  }
}

/**
 * The one sentence for someone shown the square instead of the place: why,
 * and what would change it. Only a signed-out visitor is shown the square,
 * and signing in shows the place.
 */
export const SQUARE_SENTENCE =
  "Sites like this can attract illegal metal detecting, so its exact place is kept back. Sign in to see it.";

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

/** What meets a step, from `/meta`, or undefined for a code this server's rules don't name. */
export function stepRule(meta: Meta, code: string): NextStepRule | undefined {
  return meta.vocab.next_steps.find((rule) => rule.id === code);
}

/** True for a step that a second look meets, and so is offered only blind (Decision 0008). */
export function isAnswerStep(meta: Meta, code: string): boolean {
  return stepRule(meta, code)?.met_by === "second_look";
}

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
  const rule = stepRule(meta, step.code);
  if (!position.takesWork || rule === undefined) return [];
  const actions: StepAction[] = [];
  if (rule.met_by === "second_look") {
    if (position.mayAnswer) actions.push({ kind: "answer", label: "Give a second look" });
    else if (position.isFinder) actions.push({ kind: "share", label: "Copy a link to ask others" });
    return actions;
  }
  const pending = step.pending_evidence ?? [];
  if (pending.length > 0 && !position.isFinder) {
    actions.push({ kind: "endorse", evidenceIds: pending, label: pending.length === 1 ? "See it" : "See them" });
  }
  if (!position.mayAddEvidence) return actions;
  // A step that names the strands it is missing takes only their kinds.
  const strands = step.missing_strands === undefined ? null : new Set(step.missing_strands);
  const kinds = meta.vocab.evidence_kinds.filter(
    (kind) => rule.evidence_kinds.includes(kind.id) && (strands === null || strands.has(kind.strand)),
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

/** Kinds of evidence an expert or moderator verifies before they count, as `/meta`'s step rules say. */
export function needsVerifying(meta: Meta, kindId: string): boolean {
  return meta.vocab.next_steps.some((rule) => rule.needs_verification && rule.evidence_kinds.includes(kindId));
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
  added_evidence: "added evidence",
  endorsed: "endorsed evidence",
  verified: "verified a record",
};

export function creditWords(kind: CreditKind): string {
  return CREDIT_WORDS[kind];
}
