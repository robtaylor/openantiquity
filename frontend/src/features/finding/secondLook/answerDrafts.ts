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
import { onPersonChanged } from "../../account/session.js";
import { defineDraftKind } from "../../drafts/savers.js";
import { DRAFT_KINDS, type Draft, discardDraft, listDrafts } from "../../drafts/store.js";
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

interface SavedAnswer {
  reveal: Reveal;
  /** Its place in the order answers were saved, so a page opened later can tell it is older than what it shows. */
  seq: number;
}

interface SavedAnswers {
  /** What answering revealed, by finding, for answers saved from drafts in this page and not yet shown. */
  revealed: Readonly<Record<string, SavedAnswer>>;
  record: (reveal: Reveal) => void;
  /** Forget one, once a page has dealt with it. */
  forget: (publicId: string) => void;
  clear: () => void;
}

let saves = 0;

/** How many answers have been saved from drafts so far: a page remembers this when it opens. */
export function savedAnswerCount(): number {
  return saves;
}

/**
 * Answers saved from drafts, kept until the finding's page has dealt with
 * them, so an open page can show what they revealed. What a reveal holds was
 * for the person who answered, exact place and all, so it is forgotten when
 * the person changes.
 */
export const useSavedAnswers = create<SavedAnswers>()((set) => ({
  revealed: {},
  record: (reveal) => {
    saves += 1;
    const entry = { reveal, seq: saves };
    set((state) => ({ revealed: { ...state.revealed, [reveal.finding.public_id]: entry } }));
  },
  forget: (publicId) =>
    set((state) => {
      if (!(publicId in state.revealed)) return state;
      const { [publicId]: _gone, ...rest } = state.revealed;
      return { revealed: rest };
    }),
  clear: () => set({ revealed: {} }),
}));

onPersonChanged(() => useSavedAnswers.getState().clear());

export const answerDrafts = defineDraftKind<AnswerDraftData>({
  kind: DRAFT_KINDS.observation,
  label: "Second look",
  parse: parseAnswerDraft,
  save: async (data) => {
    useSavedAnswers.getState().record(await putObservation(data.public_id, data.answer));
  },
  describe: () => "A second look",
});

/** The drafts in this browser that answer the finding: one at most, as a new answer replaces the old. */
export function answerDraftsFor(publicId: string): readonly Draft[] {
  return listDrafts().filter((draft) => answerDrafts.read(draft)?.public_id === publicId);
}

/**
 * Forget any draft answer to the finding, once an answer to it has been
 * sent another way. Left, a draft that failed to save would be offered
 * again, and the server can only refuse it, because an answer is final
 * (Decision 0008).
 */
export function discardAnswerDrafts(publicId: string): void {
  for (const draft of answerDraftsFor(publicId)) discardDraft(draft.id);
}
