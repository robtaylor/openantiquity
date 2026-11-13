import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo } from "react";
import { isTransient } from "../../api/client.js";
import type { Meta } from "../../api/meta.js";
import { useMapStore } from "../../map/store.js";
import { toast } from "../../ui/toastStore.js";
import { accountIdentity, useSession } from "../account/session.js";
import { useKindDrafts } from "../drafts/savers.js";
import { sendHeldDraft } from "../drafts/store.js";
import { giveAnswer, isShapeChanged, revealAsAsked, SHAPE_CHANGED_WORDS } from "../finding/api.js";
import { toastFailureWithRetry, useSignedInFirst } from "../finding/feedback.js";
import {
  ALREADY_FINISHED,
  type AnswerDraft,
  answerBody,
  detailBody,
  isReveal,
  newAnswer,
} from "../finding/secondLook/answer.js";
import { answerDrafts, discardAnswerDrafts, keepAnswerDraft } from "../finding/secondLook/answerDrafts.js";
import type { Reveal, Visible } from "../finding/types.js";
import { useApplyFinding } from "../finding/useFinding.js";
import { fetchReviewCards } from "./api.js";
import { reviewKeys } from "./keys.js";
import { nearFrom, pickNext } from "./queue.js";
import { useReviewStore } from "./reviewStore.js";
import type { ReviewCard } from "./types.js";

/** Cards are asked for again after this long, so the order follows other people's answers. */
const CARDS_STALE_MS = 5 * 60_000;

export type QueueStatus =
  | { kind: "loading" }
  | { kind: "card"; card: ReviewCard }
  | { kind: "empty"; skipped: number }
  | { kind: "error"; error: Error; retry: () => void };

/**
 * The card to show, from `GET /review/next`. The queue is started from where
 * the map is, so nearby findings come first, and the person moves through it
 * one card at a time: each answered, skipped or drafted card is stepped
 * past, a used-up page leads to the next, and the top is asked for again
 * once before the queue is called empty.
 */
export function useReviewQueue(): QueueStatus {
  const client = useQueryClient();
  const near = useReviewStore((state) => state.near);
  const cursor = useReviewStore((state) => state.cursor);
  const restarted = useReviewStore((state) => state.restarted);
  const current = useReviewStore((state) => state.current);
  const answered = useReviewStore((state) => state.answered);
  const skipped = useReviewStore((state) => state.skipped);
  const drafts = useKindDrafts(answerDrafts);
  const session = useSession();
  const heldBy = useReviewStore((state) => state.held?.by ?? null);
  const identity = session.me ? accountIdentity(session.me) : null;
  // A card kept from before a reload for an answer that waits for its detail is shown only to the person who gave it.
  const checking = heldBy !== null && session.status === "loading";
  const notTheirs = heldBy !== null && session.status !== "loading" && heldBy !== identity;

  useEffect(() => {
    if (notTheirs) useReviewStore.getState().drop();
  }, [notTheirs]);

  useEffect(() => {
    if (near === undefined) useReviewStore.getState().start(nearFrom(useMapStore.getState().camera));
  }, [near]);

  const started = near !== undefined;
  const query = useQuery({
    queryKey: reviewKeys.cards(near ?? null, cursor),
    queryFn: ({ signal }) => fetchReviewCards({ near: near ?? null, cursor }, signal),
    enabled: started && current === null,
    staleTime: CARDS_STALE_MS,
    retry: (failureCount, error) => failureCount < 1 && isTransient(error),
  });

  const passed = useMemo(
    () => new Set([...answered, ...skipped, ...drafts.map((draft) => draft.data.public_id)]),
    [answered, skipped, drafts],
  );
  const settled = current === null && query.data !== undefined && !query.isFetching;
  const next = settled && query.data ? pickNext(query.data, passed, restarted) : null;

  useEffect(() => {
    if (next === null) return;
    const store = useReviewStore.getState();
    if (next.kind === "card") store.show(next.card);
    else if (next.kind === "page") store.page(next.cursor);
    else if (next.kind === "restart") {
      void client.invalidateQueries({ queryKey: reviewKeys.cards(near ?? null, null) });
      store.restart();
    }
  }, [next, client, near]);

  if (checking || notTheirs) return { kind: "loading" };
  if (current) return { kind: "card", card: current };
  if (query.isError && !query.isFetching) {
    return { kind: "error", error: query.error, retry: () => void query.refetch() };
  }
  if (next?.kind === "empty") return { kind: "empty", skipped: skipped.length };
  return { kind: "loading" };
}

export interface CardAnswers {
  /**
   * Give the answer, one press. Signed in and through the welcome step, it
   * goes at once, alone, and the server holds it for its detail (Decision
   * 0008). Otherwise it is kept as a draft, replacing an earlier draft for
   * the same finding, which can still change until it is saved. Either way
   * the detail is offered next.
   */
  answer: (card: ReviewCard, visible: Visible) => Promise<void>;
  /**
   * Send the detail, or none, and see how the answer compares. Signed out,
   * the detail joins the draft, which is saved, answer first, once the
   * person has signed in; the reveal waits until then.
   */
  showComparison: (card: ReviewCard, visible: Visible, detail: AnswerDraft) => Promise<void>;
}

/** Answering the current card, in its two steps. An answer sent at once replaces a draft of it that failed. */
export function useCardAnswers(meta: Meta): CardAnswers {
  const client = useQueryClient();
  const { ready, me } = useSession();
  const signedIn = useSignedInFirst();
  const apply = useApplyFinding();
  const drafts = useKindDrafts(answerDrafts);
  const identity = me ? accountIdentity(me) : null;

  return useMemo(() => {
    const draftFor = (card: ReviewCard) => drafts.find((draft) => draft.data.public_id === card.public_id);

    function revealed(reveal: Reveal): void {
      apply(reveal.finding);
      useReviewStore.getState().revealed(reveal);
    }

    /**
     * The finder changed the shape while the person looked, so nothing was stored. Nothing of the answer is kept,
     * and the card is shown again as it now is, with its new revision, when the queue still offers it.
     */
    async function showAgain(card: ReviewCard): Promise<void> {
      toast(SHAPE_CHANGED_WORDS);
      useReviewStore.setState({ sending: null, held: null, answer: null, revealing: false });
      const { near, cursor } = useReviewStore.getState();
      void client.invalidateQueries({ queryKey: reviewKeys.all });
      try {
        const page = await fetchReviewCards({ near: near ?? null, cursor });
        const fresh = page.items.find((item) => item.public_id === card.public_id);
        if (useReviewStore.getState().current?.public_id !== card.public_id) return;
        if (fresh) useReviewStore.getState().show(fresh);
        else useReviewStore.getState().drop();
      } catch {
        if (useReviewStore.getState().current?.public_id === card.public_id) useReviewStore.getState().drop();
      }
    }

    async function answer(card: ReviewCard, visible: Visible): Promise<void> {
      const store = useReviewStore.getState();
      if (!ready || identity === null) {
        const data = {
          public_id: card.public_id,
          answer: { visible },
          reveal: false,
          shape_revision: card.shape_revision,
        };
        if (keepAnswerDraft(data, draftFor(card)?.id)) store.setAnswer(newAnswer(visible));
        return;
      }
      store.setSending(visible);
      store.setAnswer(newAnswer(visible));
      try {
        const reply = await giveAnswer(card.public_id, visible, card.shape_revision);
        // A draft of an earlier answer that failed to save is done with: this answer is the one that counts.
        discardAnswerDrafts(card.public_id);
        if (isReveal(reply)) revealed(reply);
        else useReviewStore.getState().hold({ visible, by: identity });
      } catch (error) {
        useReviewStore.setState({ sending: null, answer: null });
        if (isShapeChanged(error)) {
          await showAgain(card);
          return;
        }
        toastFailureWithRetry("Your answer couldn't be sent.", error, () => void answer(card, visible));
      }
    }

    async function showComparison(card: ReviewCard, visible: Visible, detail: AnswerDraft): Promise<void> {
      const given = { ...detail, visible };
      const held = draftFor(card);
      if (ready && identity !== null && held?.held) {
        // Given here before signing in: the person now says it is theirs, with the detail as it stands.
        const data = {
          public_id: card.public_id,
          answer: answerBody(meta, given),
          reveal: true,
          shape_revision: card.shape_revision,
        };
        if (keepAnswerDraft(data, held.id)) sendHeldDraft(held.id, identity);
        return;
      }
      if (!ready) {
        const data = {
          public_id: card.public_id,
          answer: answerBody(meta, given),
          reveal: true,
          shape_revision: card.shape_revision,
        };
        if (keepAnswerDraft(data, draftFor(card)?.id) && !(await signedIn())) {
          toast("Your answer is kept in this browser until you sign in.");
        }
        return;
      }
      useReviewStore.getState().setRevealing(true);
      try {
        revealed(await revealAsAsked(card.public_id, detailBody(meta, given), () => toast(ALREADY_FINISHED)));
      } catch (error) {
        useReviewStore.getState().setRevealing(false);
        toastFailureWithRetry("It couldn't be shown.", error, () => void showComparison(card, visible, detail));
      }
    }

    return { answer, showComparison };
  }, [meta, ready, identity, signedIn, apply, drafts, client]);
}
