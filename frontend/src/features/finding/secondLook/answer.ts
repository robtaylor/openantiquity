/**
 * A second look as the person gives it. Shared by the inline second look on
 * a finding's page and the blind queue.
 *
 * It goes in two steps (Decision 0008, docs/UI.md "Behaviour"). The answer
 * is one press and is sent at once, alone, saying its detail follows: it
 * counts, and nothing is revealed. The optional detail, what they think it
 * is and whether an ordinary explanation could account for it, is offered
 * after it, and is sent once with the request for the reveal, or left out.
 * Until then the person hasn't seen anyone else's answers, so what they say
 * it is counts as unprompted. After the reveal only the note can change.
 */

import type { Meta } from "../../../api/meta.js";
import type { FeatureClassId } from "../../findings/types.js";
import type {
  AnswerHeld,
  ExplanationId,
  Observation,
  ObservationDetailIn,
  ObservationIn,
  Reveal,
  Visible,
} from "../types.js";

/** For each ordinary explanation: "no" rules it out, "yes" gives it as the explanation. */
export type CheckAnswer = "no" | "yes" | null;

export interface AnswerDraft {
  visible: Visible;
  featureClass: string | null;
  /** By check id, such as `not_modern`. */
  checks: Readonly<Record<string, CheckAnswer>>;
  note: string;
}

export function newAnswer(visible: Visible): AnswerDraft {
  return { visible, featureClass: null, checks: {}, note: "" };
}

/**
 * The explanation a check is about: `not_modern` is about `modern`. `/meta`
 * lists checks and explanations separately, so they are matched by name.
 */
export function explanationFor(meta: Meta, checkId: string): string | null {
  const id = checkId.startsWith("not_") ? checkId.slice(4) : null;
  return id !== null && meta.vocab.explanations.some((entry) => entry.id === id) ? id : null;
}

/**
 * Give one check an answer. Only one explanation can be given, so saying
 * "yes" to one clears "yes" from the others.
 */
export function withCheck(answer: AnswerDraft, checkId: string, value: CheckAnswer): AnswerDraft {
  const checks: Record<string, CheckAnswer> = { ...answer.checks, [checkId]: value };
  if (value === "yes") {
    for (const other of Object.keys(checks)) if (other !== checkId && checks[other] === "yes") checks[other] = null;
  }
  return { ...answer, checks };
}

const CHECK_FIELDS = ["not_modern", "not_natural", "not_artefact"] as const;
type CheckField = (typeof CHECK_FIELDS)[number];

function isCheckField(id: string): id is CheckField {
  return (CHECK_FIELDS as readonly string[]).includes(id);
}

/** The request body. Only what was said is sent. */
export function answerBody(meta: Meta, answer: AnswerDraft): ObservationIn {
  const body: ObservationIn = { visible: answer.visible };
  if (answer.featureClass) body.feature_class = answer.featureClass as FeatureClassId;
  for (const [checkId, value] of Object.entries(answer.checks)) {
    if (value === "no" && isCheckField(checkId)) body[checkId] = true;
    if (value === "yes") {
      const explanation = explanationFor(meta, checkId);
      if (explanation) body.explanation = explanation as ExplanationId;
    }
  }
  const note = answer.note.trim();
  if (note) body.note = note;
  return body;
}

/** The detail alone, as `POST .../observation/reveal` takes it: only what was said. Empty skips it. */
export function detailBody(meta: Meta, answer: AnswerDraft): ObservationDetailIn {
  return detailOf(answerBody(meta, answer));
}

/** The detail in a whole answer's body: everything but the answer itself. */
export function detailOf(body: ObservationIn): ObservationDetailIn {
  const { visible: _visible, detail_follows: _follows, ...detail } = body;
  return detail;
}

/** True when the person has said anything beyond the answer. */
export function hasDetail(detail: ObservationDetailIn): boolean {
  return Object.values(detail).some((value) => value !== null && value !== undefined);
}

/** True for the reply that reveals, as opposed to one that holds an answer back for its detail. */
export function isReveal(reply: Reveal | AnswerHeld): reply is Reveal {
  return reply.revealed;
}

/** An answer kept as its request body, read back as the person gave it: `answerBody` the other way. */
export function answerFromBody(meta: Meta, body: ObservationIn): AnswerDraft {
  const checks: Record<string, CheckAnswer> = {};
  for (const check of meta.vocab.checks) {
    if (isCheckField(check.id) && body[check.id] === true) checks[check.id] = "no";
    const explanation = explanationFor(meta, check.id);
    if (explanation !== null && body.explanation === explanation) checks[check.id] = "yes";
  }
  return { visible: body.visible, featureClass: body.feature_class ?? null, checks, note: body.note ?? "" };
}

/**
 * The body that keeps an answer as given and changes only its note, or
 * restores a withdrawn one. One that was never revealed is restored still
 * waiting for its detail, so the detail is offered again.
 */
export function sameAnswer(observation: Observation, note: string | null = observation.note): ObservationIn {
  if (!observation.revealed) return { visible: observation.visible, detail_follows: true };
  const body: ObservationIn = { visible: observation.visible };
  if (observation.feature_class !== null) body.feature_class = observation.feature_class;
  if (observation.period !== null) body.period = observation.period;
  if (observation.explanation !== null) body.explanation = observation.explanation;
  if (observation.not_modern !== null) body.not_modern = observation.not_modern;
  if (observation.not_natural !== null) body.not_natural = observation.not_natural;
  if (observation.not_artefact !== null) body.not_artefact = observation.not_artefact;
  const trimmed = note?.trim();
  if (trimmed) body.note = trimmed;
  return body;
}

/** The words on each answer's button, what it means once you've given it, and someone else's. */
export const ANSWER_WORDS: Record<Visible, { button: string; given: string; theirs: string }> = {
  yes: { button: "I can see it", given: "You can see it", theirs: "Can see it" },
  unsure: { button: "Not sure", given: "You weren't sure", theirs: "Not sure" },
  no: { button: "I can't see it", given: "You can't see it", theirs: "Can't see it" },
};

/** Said when the reveal is shown without the detail given here, because another tab had already finished the answer. */
export const ALREADY_FINISHED = "Your answer was already finished in another tab, so what you added here wasn't kept.";
