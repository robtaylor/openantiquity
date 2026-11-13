/**
 * A second look given by someone not signed in is a draft in this browser
 * (Decision 0002, docs/UI.md "Behaviour"). Its data is the finding's public
 * id, the answer and any detail, as one `ObservationIn` body, and whether the
 * person asked to see how it compares. Saving it after sign-in sends them in
 * the order the API takes them: the answer alone, saying its detail follows,
 * then, if they asked for the reveal, the detail with it (Decision 0008). An
 * answer whose reveal wasn't asked for is left waiting for its detail, which
 * the finding's page or the queue then offers. The saver is registered when
 * this module loads, which the shell does at start-up through the finding's
 * page, so a draft left from before a provider's round trip is saved as soon
 * as the person is ready.
 *
 * The blind queue gives its answers through the same kind.
 */

import { useEffect, useRef } from "react";
import { create } from "zustand";
import { isRecord } from "../../../api/guards.js";
import { toast } from "../../../ui/toastStore.js";
import { onPersonChanged } from "../../account/session.js";
import { defineDraftKind, type KindDraft, useKindDrafts } from "../../drafts/savers.js";
import {
  DRAFT_KINDS,
  type Draft,
  DraftBusyError,
  DraftTooLargeError,
  discardDraft,
  listDrafts,
} from "../../drafts/store.js";
import { giveAnswer, revealAnswer } from "../api.js";
import { ANSWERS, type Observation, type ObservationIn, type Reveal } from "../types.js";
import { detailOf, isReveal } from "./answer.js";

export interface AnswerDraftData {
  public_id: string;
  answer: ObservationIn;
  /** True once the person asked to see how it compares, so saving it reveals. */
  reveal: boolean;
  /** The shape revision the answer was given on, or null for a draft made before answers named one. */
  shape_revision?: number | null;
}

export function parseAnswerDraft(value: unknown): AnswerDraftData | null {
  if (!isRecord(value) || typeof value.public_id !== "string" || value.public_id === "") return null;
  const { answer } = value;
  if (!isRecord(answer) || !(ANSWERS as readonly unknown[]).includes(answer.visible)) return null;
  // A draft from before the answer came in two steps was made by pressing "Send", which asked for the reveal.
  const reveal = value.reveal !== false;
  const revision = typeof value.shape_revision === "number" ? value.shape_revision : null;
  return { public_id: value.public_id, answer: answer as unknown as ObservationIn, reveal, shape_revision: revision };
}

/** What saving a draft gave: the reveal, or the answer held for its detail. */
export type SavedAnswer =
  | { kind: "revealed"; reveal: Reveal; seq: number }
  | { kind: "held"; observation: Observation; seq: number };

type Outcome = { kind: "revealed"; reveal: Reveal } | { kind: "held"; observation: Observation };

interface SavedAnswers {
  /** What saving answers from drafts gave, by finding, for drafts saved in this page and not yet dealt with. */
  saved: Readonly<Record<string, SavedAnswer>>;
  record: (publicId: string, outcome: Outcome) => void;
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
 * Answers saved from drafts, kept until the finding's page or the queue has
 * dealt with them, so an open page can show what they revealed or offer the
 * detail. What a reveal holds was for the person who answered, exact place
 * and all, so it is forgotten when the person changes.
 */
export const useSavedAnswers = create<SavedAnswers>()((set) => ({
  saved: {},
  record: (publicId, outcome) => {
    saves += 1;
    const entry: SavedAnswer = { ...outcome, seq: saves };
    set((state) => ({ saved: { ...state.saved, [publicId]: entry } }));
  },
  forget: (publicId) =>
    set((state) => {
      if (!(publicId in state.saved)) return state;
      const { [publicId]: _gone, ...rest } = state.saved;
      return { saved: rest };
    }),
  clear: () => set({ saved: {} }),
}));

onPersonChanged(() => useSavedAnswers.getState().clear());

/**
 * Send a drafted answer as the API takes it: the answer, then the detail
 * with the reveal if it was asked for. Sent again after a failure, the first
 * step finds the answer already in and the second the same detail, so
 * nothing is given twice.
 */
async function saveAnswer(data: AnswerDraftData): Promise<Outcome> {
  const first = await giveAnswer(data.public_id, data.answer.visible, data.shape_revision ?? null);
  if (isReveal(first)) return { kind: "revealed", reveal: first };
  if (!data.reveal) return { kind: "held", observation: first.observation };
  return { kind: "revealed", reveal: await revealAnswer(data.public_id, detailOf(data.answer)) };
}

export const answerDrafts = defineDraftKind<AnswerDraftData>({
  kind: DRAFT_KINDS.observation,
  label: "Second look",
  parse: parseAnswerDraft,
  save: async (data) => {
    useSavedAnswers.getState().record(data.public_id, await saveAnswer(data));
  },
  describe: () => "A second look",
});

/**
 * Keep a signed-out answer, with any detail, as the finding's draft,
 * replacing `id` when given. False, said in a toast, when the browser can't
 * keep it or it is being saved this moment.
 */
export function keepAnswerDraft(data: AnswerDraftData, id?: string): boolean {
  try {
    answerDrafts.put(data, id);
    return true;
  } catch (error) {
    if (error instanceof DraftTooLargeError || error instanceof DraftBusyError) {
      toast(error.message, { kind: "error" });
      return false;
    }
    throw error;
  }
}

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

/**
 * True when a kept answer was given on another shape than the one shown at
 * revision `shown`. An answer names the shape it was given on, and one kept
 * before answers named a revision was given on revision 0.
 */
export function givenOnAnotherShape(data: AnswerDraftData, shown: number | null | undefined): boolean {
  return (data.shape_revision ?? 0) !== (shown ?? 0);
}

/**
 * The answer kept in this browser for the finding, if it was given on the
 * shape shown at `revision`. Nothing of an answer to a shape that has since
 * changed is kept: such a draft is never offered, it is removed, and
 * `onStale` is called once so the page can say the shape changed.
 */
export function useAnswerDraftOn(
  publicId: string,
  revision: number | null | undefined,
  onStale: () => void,
): KindDraft<AnswerDraftData> | null {
  const draft = useKindDrafts(answerDrafts).find((entry) => entry.data.public_id === publicId) ?? null;
  const staleId = draft !== null && givenOnAnotherShape(draft.data, revision) ? draft.id : null;
  const latest = useRef(onStale);
  latest.current = onStale;
  const removed = useRef<string | null>(null);
  useEffect(() => {
    if (staleId === null || removed.current === staleId) return;
    removed.current = staleId;
    discardDraft(staleId);
    latest.current();
  }, [staleId]);
  return staleId === null ? draft : null;
}
