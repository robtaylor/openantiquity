/**
 * A second look given by someone not signed in is a draft in this browser
 * (Decision 0002, docs/UI.md "Behaviour"). Its data is the finding's public
 * id and the body `PUT /findings/{id}/observation` will be sent, so saving it
 * after sign-in sends exactly what was answered. The saver is registered
 * when this module loads, which the shell does at start-up through the
 * finding's page, so a draft left from before a provider's round trip is
 * saved as soon as the person is ready.
 *
 * The blind queue gives its answers through the same kind.
 */

import { create } from "zustand";
import { isRecord } from "../../../api/guards.js";
import { defineDraftKind } from "../../drafts/savers.js";
import { DRAFT_KINDS } from "../../drafts/store.js";
import { putObservation } from "../api.js";
import { ANSWERS, type ObservationIn, type Reveal } from "../types.js";

export interface AnswerDraftData {
  public_id: string;
  answer: ObservationIn;
}

export function parseAnswerDraft(value: unknown): AnswerDraftData | null {
  if (!isRecord(value) || typeof value.public_id !== "string" || value.public_id === "") return null;
  const { answer } = value;
  if (!isRecord(answer) || !(ANSWERS as readonly unknown[]).includes(answer.visible)) return null;
  return { public_id: value.public_id, answer: answer as unknown as ObservationIn };
}

interface SavedAnswers {
  /** What answering revealed, by finding, for answers saved from drafts in this page. */
  revealed: Readonly<Record<string, Reveal>>;
  record: (reveal: Reveal) => void;
}

/** Answers saved from drafts since the page loaded, so an open page can show what they revealed. */
export const useSavedAnswers = create<SavedAnswers>()((set) => ({
  revealed: {},
  record: (reveal) => set((state) => ({ revealed: { ...state.revealed, [reveal.finding.public_id]: reveal } })),
}));

export const answerDrafts = defineDraftKind<AnswerDraftData>({
  kind: DRAFT_KINDS.observation,
  label: "Second look",
  parse: parseAnswerDraft,
  save: async (data) => {
    useSavedAnswers.getState().record(await putObservation(data.public_id, data.answer));
  },
  describe: () => "A second look",
});
