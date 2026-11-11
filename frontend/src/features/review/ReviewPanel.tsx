import { Coffee, HandHelping, LogIn, RotateCcw, ScanSearch, Send, SkipForward, Unplug } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router";
import type { Meta } from "../../api/meta.js";
import { Button } from "../../ui/Button.js";
import { EmptyState } from "../../ui/EmptyState.js";
import { Skeleton } from "../../ui/Skeleton.js";
import { useSession } from "../account/session.js";
import { DraftBadge } from "../drafts/DraftBadge.js";
import { type KindDraft, useKindDrafts } from "../drafts/savers.js";
import { reasonOf, useSignedInFirst } from "../finding/feedback.js";
import { AnswerButtons } from "../finding/secondLook/AnswerButtons.js";
import { AnswerDetail } from "../finding/secondLook/AnswerDetail.js";
import { ANSWER_WORDS, answerFromBody, newAnswer } from "../finding/secondLook/answer.js";
import { type AnswerDraftData, answerDrafts } from "../finding/secondLook/answerDrafts.js";
import type { Visible } from "../finding/types.js";
import { useDocumentTitle } from "../placeholders.js";
import { PanelFrame } from "../shell/PanelFrame.js";
import { usePanelEnvironment } from "../shell/panelContext.js";
import { RevealCard } from "./RevealCard.js";
import { REVIEW_PATH } from "./ReviewLayer.js";
import { useReviewStore } from "./reviewStore.js";
import type { ReviewCard } from "./types.js";
import { useAnswerKeys } from "./useAnswerKeys.js";
import { useReviewQueue, useSendAnswer } from "./useReviewQueue.js";
import "../finding/finding.css";
import "./review.css";

/** The title of the panel and the page, the same whatever the card: it never names a finding. */
export const REVIEW_TITLE = "Second look";

/** The three answers, then the optional detail and the button that sends it all. */
function Ask({ meta, card, draft }: { meta: Meta; card: ReviewCard; draft: KindDraft<AnswerDraftData> | null }) {
  const answer = useReviewStore((state) => state.answer);
  const sending = useReviewStore((state) => state.sending);
  const { setAnswer, skip } = useReviewStore.getState();
  const { ready } = useSession();
  const { isPhone } = usePanelEnvironment();
  const send = useSendAnswer(meta);

  function choose(visible: Visible): void {
    if (sending) return;
    const now = useReviewStore.getState().answer;
    setAnswer(now ? { ...now, visible } : newAnswer(visible));
  }
  useAnswerKeys(!sending, choose);

  return (
    <div className="fc-review__ask">
      <p className="fc-review__intro">
        A second look is someone else checking a finding without being told what its finder thought. Look in the frame
        on the map, in the view the finder used. Can you see a feature there?
      </p>
      <p className="fc-review__place">
        At <span className="fc-mono">{card.place.grid_ref ?? "this place"}</span>
      </p>
      <AnswerButtons value={answer?.visible ?? null} onChoose={choose} disabled={sending} keyHints={!isPhone} />
      <p className="fc-finding__hint">
        {isPhone ? "" : "Press 1, 2 or 3 to answer. "}
        You'll see what the finder thought, and what others said, once you've sent your answer.
      </p>
      {answer ? (
        <>
          <AnswerDetail meta={meta} answer={answer} onChange={setAnswer} />
          <div className="fc-second-look__send">
            <Button
              variant="primary"
              block
              icon={<Send size={16} aria-hidden />}
              disabled={sending}
              onClick={() => void send(card, answer)}
            >
              {sending ? "Sending…" : `Send “${ANSWER_WORDS[answer.visible].button}”`}
            </Button>
            <p className="fc-finding__hint">
              {ready
                ? "Once it's sent, your answer is final."
                : "You're not signed in, so it's kept in this browser until you are. You can change it until then."}
            </p>
            {draft ? (
              <Button size="sm" variant="ghost" disabled={sending} onClick={() => setAnswer(null)}>
                Keep the answer I gave
              </Button>
            ) : null}
          </div>
        </>
      ) : null}
      {draft ? null : (
        <div className="fc-review__skip">
          <Button
            size="sm"
            variant="ghost"
            icon={<SkipForward size={15} aria-hidden />}
            disabled={sending}
            onClick={skip}
          >
            Skip this one
          </Button>
          <span className="fc-finding__hint">Skipping says nothing about the finding.</span>
        </div>
      )}
    </div>
  );
}

/** An answer kept in this browser: not saved, so it can still change, and nothing is revealed yet. */
function DraftKept({ meta, draft }: { meta: Meta; draft: KindDraft<AnswerDraftData> }) {
  const signedIn = useSignedInFirst();
  const { ready } = useSession();
  const { setAnswer, next } = useReviewStore.getState();
  const saving = draft.state === "saving" || (ready && draft.state === "waiting");
  let status: string;
  if (saving) status = "Saving your answer…";
  else if (draft.state === "failed")
    status = `It couldn't be saved. ${draft.failure?.message ?? "Something went wrong."} The drafts bar can try again.`;
  else
    status =
      "It's kept in this browser until you sign in. Until then you can change it. Once it's saved it's final, and you'll see what the finder and others said.";
  return (
    <div className="fc-given fc-review__draft">
      <p>
        <strong>{ANSWER_WORDS[draft.data.answer.visible].given}.</strong> <DraftBadge />
      </p>
      <p className="fc-finding__hint" role="status">
        {status}
      </p>
      <div className="fc-given__actions">
        {ready ? null : (
          <Button size="sm" variant="primary" icon={<LogIn size={15} aria-hidden />} onClick={() => void signedIn()}>
            Sign in to save it
          </Button>
        )}
        <Button size="sm" disabled={saving} onClick={() => setAnswer(answerFromBody(meta, draft.data.answer))}>
          Change my answer
        </Button>
        <Button size="sm" variant="ghost" onClick={next}>
          Next finding
        </Button>
      </div>
    </div>
  );
}

function CardView({ meta, card }: { meta: Meta; card: ReviewCard }) {
  const reveal = useReviewStore((state) => state.reveal);
  const editing = useReviewStore((state) => state.answer !== null);
  const draft = useKindDrafts(answerDrafts).find((entry) => entry.data.public_id === card.public_id) ?? null;
  if (reveal) return <RevealCard meta={meta} reveal={reveal} onNext={useReviewStore.getState().next} />;
  if (draft && !editing) return <DraftKept meta={meta} draft={draft} />;
  return <Ask meta={meta} card={card} draft={draft} />;
}

function EmptyQueue({ skipped }: { skipped: number }) {
  return (
    <EmptyState
      icon={<Coffee size={22} />}
      title="Nothing waiting just now"
      action={
        <div className="fc-review__empty-actions">
          <Link className="fc-button fc-button--primary fc-button--md" to="/scan">
            <ScanSearch size={16} aria-hidden />
            Scan a square
          </Link>
          <Link className="fc-button fc-button--secondary fc-button--md" to="/help">
            <HandHelping size={16} aria-hidden />
            Help wanted
          </Link>
          {skipped > 0 ? (
            <Button
              variant="ghost"
              icon={<RotateCcw size={16} aria-hidden />}
              onClick={useReviewStore.getState().revisitSkipped}
            >
              Look at the {skipped === 1 ? "one" : `${skipped}`} you skipped
            </Button>
          ) : null}
        </div>
      }
    >
      <p>
        Thank you for looking. New ones arrive as people mark findings. Meanwhile, you could scan a square nobody has
        looked at yet, or help with the next step on someone's finding.
      </p>
    </EmptyState>
  );
}

/**
 * Second look, at `/review`: findings waiting for another pair of eyes, one
 * at a time, blind (Decision 0008). Before an answer the card is the place
 * and the finder's view, and nothing else: no title, class, description,
 * tier or count is asked for, kept or shown, and the panel's title and the
 * address stay the same for every card.
 */
export function ReviewPanel({ meta }: { meta: Meta }) {
  useDocumentTitle(REVIEW_TITLE);
  const status = useReviewQueue();
  let body: ReactNode;
  switch (status.kind) {
    case "loading":
      body = (
        <div role="status" className="fc-review__loading">
          <span className="fc-visually-hidden">Finding one for you to look at</span>
          <Skeleton lines={3} />
          <Skeleton height={72} />
        </div>
      );
      break;
    case "error":
      body = (
        <EmptyState
          tone="error"
          icon={<Unplug size={22} />}
          title="The next finding couldn't be fetched"
          action={
            <Button variant="primary" onClick={status.retry}>
              Try again
            </Button>
          }
        >
          <p>{reasonOf(status.error)}</p>
        </EmptyState>
      );
      break;
    case "empty":
      body = <EmptyQueue skipped={status.skipped} />;
      break;
    case "card":
      body = <CardView meta={meta} card={status.card} />;
      break;
  }
  return (
    <PanelFrame panelKey={REVIEW_PATH} title={REVIEW_TITLE}>
      <div className="fc-review">{body}</div>
    </PanelFrame>
  );
}
