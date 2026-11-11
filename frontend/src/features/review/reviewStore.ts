/**
 * Where the person is in the second-look queue. It lives outside the panel
 * because the shell takes the panel away while the layer panel is open over
 * it, and changing layer mustn't end a second look (docs/UI.md, "Layout").
 *
 * What it holds before an answer is what the card holds: a public id, a
 * place and a view. Nothing about the finder's claim is kept until the
 * answer's reply reveals it (Decision 0008).
 *
 * While the current card's answer is waiting as a draft, the card is also
 * kept in this tab's `sessionStorage`, so that a provider's sign-in, which
 * reloads the page, comes back to it. It is written only while that draft
 * exists, removed as soon as it doesn't, and read back only when the draft
 * is still there, because a card's place is exact and the next person may
 * not be allowed to see it (Decision 0005).
 */

import { create } from "zustand";
import { isRecord } from "../../api/guards.js";
import { onPersonChanged } from "../account/session.js";
import { subscribeDrafts } from "../drafts/store.js";
import type { AnswerDraft } from "../finding/secondLook/answer.js";
import { answerDraftsFor } from "../finding/secondLook/answerDrafts.js";
import type { Reveal } from "../finding/types.js";
import type { ReviewCard } from "./types.js";

export const CARD_STORAGE_KEY = "fieldclub.review.card";

export interface ReviewState {
  /** Where the queue was started, for its order. Undefined until it is started. */
  near: [number, number] | null | undefined;
  /** The page of cards being worked through. */
  cursor: string | null;
  /** True once the queue has been asked again from the top since the last card was shown. */
  restarted: boolean;
  current: ReviewCard | null;
  /** The answer being chosen for the current card, before it is sent. */
  answer: AnswerDraft | null;
  sending: boolean;
  /** What answering the current card revealed. */
  reveal: Reveal | null;
  /** Cards answered or skipped in this visit, by public id. */
  answered: readonly string[];
  skipped: readonly string[];

  start: (near: [number, number] | null) => void;
  show: (card: ReviewCard) => void;
  setAnswer: (answer: AnswerDraft | null) => void;
  setSending: (sending: boolean) => void;
  revealed: (reveal: Reveal) => void;
  /** Done with the current card, answered: on to the next. */
  next: () => void;
  /** Leave the current card unanswered. It says nothing about the finding. */
  skip: () => void;
  page: (cursor: string) => void;
  restart: () => void;
  /** Bring back the cards skipped in this visit. */
  revisitSkipped: () => void;
  reset: () => void;
}

function parseStoredCard(raw: string | null): ReviewCard | null {
  if (raw === null) return null;
  try {
    const value: unknown = JSON.parse(raw);
    if (!isRecord(value) || typeof value.public_id !== "string" || !isRecord(value.place)) return null;
    const card = value as unknown as ReviewCard;
    return hasDraft(card.public_id) ? card : null;
  } catch {
    return null;
  }
}

/** The card kept over a provider's round trip, if its draft is still here. A copy that isn't wanted is removed. */
export function readStoredCard(): ReviewCard | null {
  let raw: string | null = null;
  try {
    raw = sessionStorage.getItem(CARD_STORAGE_KEY);
  } catch {
    return null;
  }
  const card = parseStoredCard(raw);
  if (card === null && raw !== null) storeCard(null);
  return card;
}

function storeCard(card: ReviewCard | null): void {
  try {
    if (card === null) sessionStorage.removeItem(CARD_STORAGE_KEY);
    else sessionStorage.setItem(CARD_STORAGE_KEY, JSON.stringify(card));
  } catch {
    // A browser that won't store it loses the card over a provider's round trip. The draft is kept either way.
  }
}

/** True when this browser holds an answer to the finding as a draft. */
export function hasDraft(publicId: string): boolean {
  return answerDraftsFor(publicId).length > 0;
}

const FRESH = {
  near: undefined,
  cursor: null,
  restarted: false,
  current: null,
  answer: null,
  sending: false,
  reveal: null,
  answered: [],
  skipped: [],
} satisfies Partial<ReviewState>;

/** What moving off a card clears. */
const OFF_CARD = { current: null, answer: null, sending: false, reveal: null } satisfies Partial<ReviewState>;

export const useReviewStore = create<ReviewState>()((set, get) => ({
  ...FRESH,
  current: readStoredCard(),

  start: (near) => set({ near, cursor: null, restarted: false }),
  show: (card) => set({ ...OFF_CARD, current: card, restarted: false }),
  setAnswer: (answer) => set({ answer }),
  setSending: (sending) => set({ sending }),
  revealed: (reveal) => {
    if (get().current?.public_id !== reveal.finding.public_id) return;
    set({ reveal, sending: false, answer: null });
  },
  next: () => {
    const { current, answered } = get();
    set({ ...OFF_CARD, answered: current ? [...answered, current.public_id] : answered });
  },
  skip: () => {
    const { current, skipped } = get();
    set({ ...OFF_CARD, skipped: current ? [...skipped, current.public_id] : skipped });
  },
  page: (cursor) => set({ cursor }),
  restart: () => set({ cursor: null, restarted: true }),
  revisitSkipped: () => set({ skipped: [], cursor: null, restarted: false }),
  reset: () => set({ ...FRESH }),
}));

/** Keep the current card in `sessionStorage` exactly while its answer is waiting as a draft. */
function keepCardForSignIn(): void {
  const { current } = useReviewStore.getState();
  storeCard(current !== null && hasDraft(current.public_id) ? current : null);
}

useReviewStore.subscribe((next, previous) => {
  if (next.current !== previous.current) keepCardForSignIn();
});
subscribeDrafts(keepCardForSignIn);

// A new person gets a queue of their own. The card stays only when its answer is waiting as their draft.
onPersonChanged(() => {
  const { current } = useReviewStore.getState();
  const keep = current !== null && hasDraft(current.public_id) ? current : null;
  useReviewStore.setState({ ...FRESH, current: keep });
});
