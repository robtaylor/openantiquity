/**
 * A second look as the person gives it, and the body `PUT
 * /findings/{id}/observation` is sent. Shared by the inline second look on a
 * finding's page and the blind queue.
 *
 * An answer is final once sent (Decision 0008): only its note can change
 * afterwards. So the optional detail, what they think it is and whether
 * there is an ordinary explanation, is offered once the answer is chosen and
 * goes with it.
 */

import type { Meta } from "../../../api/meta.js";
import type { FeatureClassId } from "../../findings/types.js";
import type { ExplanationId, Observation, ObservationIn, Visible } from "../types.js";

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

/** The body that keeps an answer as given and changes only its note, or restores a withdrawn one. */
export function sameAnswer(observation: Observation, note: string | null = observation.note): ObservationIn {
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
