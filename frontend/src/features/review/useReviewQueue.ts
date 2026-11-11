import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo } from "react";
import { isTransient } from "../../api/client.js";
import type { Meta } from "../../api/meta.js";
import { useMapStore } from "../../map/store.js";
import { toast } from "../../ui/toastStore.js";
import { useSession } from "../account/session.js";
import { useKindDrafts } from "../drafts/savers.js";
import { DraftBusyError, DraftTooLargeError } from "../drafts/store.js";
import { putObservation } from "../finding/api.js";
import { reasonOf, useSignedInFirst } from "../finding/feedback.js";
import { type AnswerDraft, answerBody } from "../finding/secondLook/answer.js";
import { answerDrafts } from "../finding/secondLook/answerDrafts.js";
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

  if (current) return { kind: "card", card: current };
  if (query.isError && !query.isFetching) {
    return { kind: "error", error: query.error, retry: () => void query.refetch() };
  }
  if (next?.kind === "empty") return { kind: "empty", skipped: skipped.length };
  return { kind: "loading" };
}

/**
 * Send the answer to the current card. Signed in and through the welcome
 * step, it goes at once and the reply reveals the finding. Otherwise it is
 * kept as a draft (replacing an earlier draft for the same finding, which
 * can still be changed until it is saved) and the sign-in sheet opens; the
 * reveal waits until the drafts machinery has saved it.
 */
export function useSendAnswer(meta: Meta): (card: ReviewCard, answer: AnswerDraft) => Promise<void> {
  const { ready } = useSession();
  const signedIn = useSignedInFirst();
  const apply = useApplyFinding();
  const drafts = useKindDrafts(answerDrafts);

  return useCallback(
    async function send(card: ReviewCard, answer: AnswerDraft): Promise<void> {
      const body = answerBody(meta, answer);
      const store = useReviewStore.getState();
      if (!ready) {
        const existing = drafts.find((draft) => draft.data.public_id === card.public_id);
        try {
          answerDrafts.put({ public_id: card.public_id, answer: body }, existing?.id);
        } catch (error) {
          if (error instanceof DraftTooLargeError || error instanceof DraftBusyError) {
            toast(error.message, { kind: "error" });
            return;
          }
          throw error;
        }
        store.setAnswer(null);
        if (!(await signedIn())) {
          toast("Your answer is kept in this browser. Sign in when you're ready, and it will be saved.");
        }
        return;
      }
      store.setSending(true);
      try {
        const reveal = await putObservation(card.public_id, body);
        apply(reveal.finding);
        useReviewStore.getState().revealed(reveal);
      } catch (error) {
        useReviewStore.getState().setSending(false);
        toast(`Your answer couldn't be sent. ${reasonOf(error)}`, {
          kind: "error",
          duration: 0,
          action: { label: "Try again", onClick: () => void send(card, answer) },
        });
      }
    },
    [meta, ready, signedIn, apply, drafts],
  );
}
