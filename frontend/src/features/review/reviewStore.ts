/**
 * Where the person is in the second-look queue. It lives outside the panel
 * because the shell takes the panel away while the layer panel is open over
 * it, and changing layer mustn't end a second look (docs/UI.md, "Layout").
 *
 * What it holds before the reveal is what the card holds: a public id, a
 * place and a view, and the person's own answer. Nothing about the finder's
 * claim is kept until the reveal's reply shows it (Decision 0008).
 *
 * A card's answer goes in two steps: the answer alone, sent at once, which
 * the server holds (`held`), then the optional detail with the request for
 * the reveal. While the current card's answer waits for its detail, or waits
 * as a draft, the card is also kept in this tab's `sessionStorage`, so a
 * reload or a provider's sign-in comes back to it. It is written only while
 * one of those is true, removed as soon as neither is, and read back only
 * when its draft is still there or for the person whose answer it holds,
 * because a card's place is exact and the next person may not be allowed to
 * see it (Decision 0005).
 */

import { create } from "zustand";
import { isRecord } from "../../api/guards.js";
import { onPersonChanged } from "../account/session.js";
import { subscribeDrafts } from "../drafts/store.js";
import type { AnswerDraft } from "../finding/secondLook/answer.js";
import { answerDraftsFor } from "../finding/secondLook/answerDrafts.js";
import { ANSWERS, type Reveal, type Visible } from "../finding/types.js";
import type { ReviewCard } from "./types.js";

export const CARD_STORAGE_KEY = "fieldclub.review.card";

/** The current card's answer, in and counting, waiting for its detail: the answer, and whose it is. */
export interface HeldAnswer {
  visible: Visible;
  /** The account that gave it (`accountIdentity`). */
  by: string;
}

export interface ReviewState {
  /** Where the queue was started, for its order. Undefined until it is started. */
  near: [number, number] | null | undefined;
  /** The page of cards being worked through. */
  cursor: string | null;
  /** True once the queue has been asked again from the top since the last card was shown. */
  restarted: boolean;
  current: ReviewCard | null;
  /** The answer pressed for the current card and on its way to the server. */
  sending: Visible | null;
  /** The current card's answer once the server has it, until the reveal. */
  held: HeldAnswer | null;
  /** The detail being given, once the answer is in or kept as a draft. */
  answer: AnswerDraft | null;
  /** True while the reveal is on its way. */
  revealing: boolean;
  /** What answering the current card revealed. */
  reveal: Reveal | null;
  /** Cards answered or skipped in this visit, by public id. */
  answered: readonly string[];
  skipped: readonly string[];

  start: (near: [number, number] | null) => void;
  show: (card: ReviewCard) => void;
  setAnswer: (answer: AnswerDraft | null) => void;
  setSending: (sending: Visible | null) => void;
  /** The server holds the current card's answer for its detail. */
  hold: (held: HeldAnswer) => void;
  setRevealing: (revealing: boolean) => void;
  revealed: (reveal: Reveal) => void;
  /** Done with the current card, answered: on to the next. */
  next: () => void;
  /** Leave the current card unanswered. It says nothing about the finding. */
  skip: () => void;
  /** Let go of a card kept from before a reload that isn't this person's to see. */
  drop: () => void;
  page: (cursor: string) => void;
  restart: () => void;
  /** Bring back the cards skipped in this visit. */
  revisitSkipped: () => void;
  reset: () => void;
}

interface Stored {
  card: ReviewCard;
  held: HeldAnswer | null;
}

function readHeld(value: unknown): HeldAnswer | null {
  if (!isRecord(value) || typeof value.by !== "string" || value.by === "") return null;
  return (ANSWERS as readonly unknown[]).includes(value.visible)
    ? { visible: value.visible as Visible, by: value.by }
    : null;
}

function parseStored(raw: string | null): Stored | null {
  if (raw === null) return null;
  try {
    const value: unknown = JSON.parse(raw);
    if (!isRecord(value) || typeof value.public_id !== "string" || !isRecord(value.place)) return null;
    const { held, ...card } = value;
    const stored: Stored = { card: card as unknown as ReviewCard, held: readHeld(held) };
    return stored.held !== null || hasDraft(stored.card.public_id) ? stored : null;
  } catch {
    return null;
  }
}

/**
 * The card kept over a reload or a provider's round trip, if its draft is
 * still here or its answer waits for its detail. A copy that isn't wanted
 * is removed. A held answer is checked against who is signed in before the
 * card is shown (`useReviewQueue`).
 */
export function readStored(): Stored | null {
  let raw: string | null = null;
  try {
    raw = sessionStorage.getItem(CARD_STORAGE_KEY);
  } catch {
    return null;
  }
  const stored = parseStored(raw);
  if (stored === null && raw !== null) store(null);
  return stored;
}

/** The card alone, as `readStored` gives it. */
export function readStoredCard(): ReviewCard | null {
  return readStored()?.card ?? null;
}

function store(kept: Stored | null): void {
  try {
    if (kept === null) sessionStorage.removeItem(CARD_STORAGE_KEY);
    else sessionStorage.setItem(CARD_STORAGE_KEY, JSON.stringify({ ...kept.card, held: kept.held }));
  } catch {
    // A browser that won't store it loses the card over a reload. The draft, or the server's answer, is kept either way.
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
  sending: null,
  held: null,
  answer: null,
  revealing: false,
  reveal: null,
  answered: [],
  skipped: [],
} satisfies Partial<ReviewState>;

/** What moving off a card clears. */
const OFF_CARD = {
  current: null,
  sending: null,
  held: null,
  answer: null,
  revealing: false,
  reveal: null,
} satisfies Partial<ReviewState>;

const kept = readStored();

export const useReviewStore = create<ReviewState>()((set, get) => ({
  ...FRESH,
  current: kept?.card ?? null,
  held: kept?.held ?? null,

  start: (near) => set({ near, cursor: null, restarted: false }),
  show: (card) => set({ ...OFF_CARD, current: card, restarted: false }),
  setAnswer: (answer) => set({ answer }),
  setSending: (sending) => set({ sending }),
  hold: (held) => set({ held, sending: null }),
  setRevealing: (revealing) => set({ revealing }),
  revealed: (reveal) => {
    if (get().current?.public_id !== reveal.finding.public_id) return;
    set({ reveal, sending: null, held: null, revealing: false, answer: null });
  },
  next: () => {
    const { current, answered } = get();
    set({ ...OFF_CARD, answered: current ? [...answered, current.public_id] : answered });
  },
  skip: () => {
    const { current, skipped } = get();
    set({ ...OFF_CARD, skipped: current ? [...skipped, current.public_id] : skipped });
  },
  drop: () => set({ ...OFF_CARD }),
  page: (cursor) => set({ cursor }),
  restart: () => set({ cursor: null, restarted: true }),
  revisitSkipped: () => set({ skipped: [], cursor: null, restarted: false }),
  reset: () => set({ ...FRESH }),
}));

/** Keep the current card in `sessionStorage` exactly while its answer waits for its detail or as a draft. */
function keepCard(): void {
  const { current, held } = useReviewStore.getState();
  store(current !== null && (held !== null || hasDraft(current.public_id)) ? { card: current, held } : null);
}

useReviewStore.subscribe((next, previous) => {
  if (next.current !== previous.current || next.held !== previous.held) keepCard();
});
subscribeDrafts(keepCard);

// A new person gets a queue of their own. The card stays only when its answer is waiting as their draft.
onPersonChanged(() => {
  const { current } = useReviewStore.getState();
  const keep = current !== null && hasDraft(current.public_id) ? current : null;
  useReviewStore.setState({ ...FRESH, current: keep });
});
