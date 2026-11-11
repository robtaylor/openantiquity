import { Coffee, HandHelping, RotateCcw, ScanSearch, SkipForward, Unplug } from "lucide-react";
import { type ReactNode, type RefObject, useEffect, useRef } from "react";
import { Link } from "react-router";
import type { Meta } from "../../api/meta.js";
import { Button } from "../../ui/Button.js";
import { EmptyState } from "../../ui/EmptyState.js";
import { Skeleton } from "../../ui/Skeleton.js";
import { useSession } from "../account/session.js";
import { type KindDraft, useKindDrafts } from "../drafts/savers.js";
import { discardDraft } from "../drafts/store.js";
import { reasonOf } from "../finding/feedback.js";
import { AnswerButtons } from "../finding/secondLook/AnswerButtons.js";
import { answerFromBody, newAnswer } from "../finding/secondLook/answer.js";
import { type AnswerDraftData, answerDrafts } from "../finding/secondLook/answerDrafts.js";
import { DetailStep, FailedDraftNotice } from "../finding/secondLook/DetailStep.js";
import { useAnswerInSight } from "../finding/secondLook/useAnswerInSight.js";
import type { Visible } from "../finding/types.js";
import { useDocumentTitle } from "../placeholders.js";
import { PanelFrame } from "../shell/PanelFrame.js";
import { usePanelEnvironment } from "../shell/panelContext.js";
import { RevealCard } from "./RevealCard.js";
import { REVIEW_PATH } from "./ReviewLayer.js";
import { useReviewStore } from "./reviewStore.js";
import type { ReviewCard } from "./types.js";
import { useAnswerKeys } from "./useAnswerKeys.js";
import { useCardAnswers, useReviewQueue } from "./useReviewQueue.js";
import "../finding/finding.css";
import "./review.css";

/** The title of the panel and the page, the same whatever the card: it never names a finding. */
export const REVIEW_TITLE = "Second look";

/** Bring the phone sheet down to half-way before the next card, so the map moves to it in sight. */
function useSheetDownThen(): (then: () => void) => () => void {
  const { isPhone, stop, setStop } = usePanelEnvironment();
  return (then) => () => {
    if (isPhone && stop === "full") setStop("half");
    then();
  };
}

/**
 * The three answers, each sent with one press, and skipping. `byKey` notes
 * whether the answer was given by its key, for where focus goes next.
 */
function Ask({
  meta,
  card,
  byKey,
  failed,
}: {
  meta: Meta;
  card: ReviewCard;
  byKey: RefObject<boolean | null>;
  /** An answer to this card kept as a draft that failed to save, and why. */
  failed: KindDraft<AnswerDraftData> | null;
}) {
  const sending = useReviewStore((state) => state.sending !== null);
  const { skip } = useReviewStore.getState();
  const { isPhone, shouldTakeFocus } = usePanelEnvironment();
  const { answer } = useCardAnswers(meta);
  const sheetDownThen = useSheetDownThen();
  const question = useRef<HTMLParagraphElement>(null);

  // Each card starts at its question, so the keyboard and a screen reader start there too, not from the top of
  // the page: unless focus is somewhere else on purpose, or the page has only just loaded (see `PanelFrame`).
  // biome-ignore lint/correctness/useExhaustiveDependencies: a new card is the trigger
  useEffect(() => {
    const active = document.activeElement;
    const lost = active === null || active === document.body;
    const inPanel = active !== null && question.current?.closest(".fc-panel")?.contains(active) === true;
    if (inPanel || (lost && shouldTakeFocus())) question.current?.focus({ preventScroll: true });
  }, [card.public_id]);

  function choose(visible: Visible, viaKey: boolean): void {
    if (useReviewStore.getState().sending !== null) return;
    byKey.current = viaKey;
    void answer(card, visible);
  }
  useAnswerKeys(!sending, (visible) => choose(visible, true));

  return (
    <div className="fc-review__ask">
      <p className="fc-review__intro" ref={question} tabIndex={-1}>
        A second look is someone else checking a finding without being told what its finder thought. Look in the frame
        on the map, in the view the finder used. Can you see a feature there?
      </p>
      <p className="fc-review__place">
        At <span className="fc-mono">{card.place.grid_ref ?? "this place"}</span>
      </p>
      {failed ? <FailedDraftNotice message={failed.failure?.message} /> : null}
      <AnswerButtons
        value={null}
        onChoose={(visible) => choose(visible, false)}
        disabled={sending}
        keyHints={!isPhone}
      />
      <p className="fc-finding__hint">
        {isPhone ? "" : "Press 1, 2 or 3 to answer. "}
        Your answer counts as soon as you give it. Then you can say more, and see what the finder thought and what
        others said.
      </p>
      <div className="fc-review__skip">
        <Button
          size="sm"
          variant="ghost"
          icon={<SkipForward size={15} aria-hidden />}
          disabled={sending}
          onClick={sheetDownThen(skip)}
        >
          Skip this one
        </Button>
        <span className="fc-finding__hint">Skipping says nothing about the finding.</span>
      </div>
    </div>
  );
}

/**
 * The answer is in, or kept as a draft: the optional detail, then the
 * comparison. Straight after an answer, focus goes to the line saying it is
 * in, so the detail is read next, or after an answer given by its key to the
 * button, so a number and Enter answer a card.
 */
function Detail({
  meta,
  card,
  visible,
  draft,
  focus,
}: {
  meta: Meta;
  card: ReviewCard;
  visible: Visible;
  draft: KindDraft<AnswerDraftData> | null;
  focus: "given" | "reveal" | null;
}) {
  const sending = useReviewStore((state) => state.sending !== null);
  const held = useReviewStore((state) => state.held !== null);
  const revealing = useReviewStore((state) => state.revealing);
  const answer = useReviewStore((state) => state.answer);
  const { ready } = useSession();
  const { showComparison } = useCardAnswers(meta);
  const detail = answer ?? (draft ? answerFromBody(meta, draft.data.answer) : newAnswer(visible));
  const savingDraft = draft !== null && !held && ready;

  return (
    <div className="fc-review__ask">
      <p className="fc-review__place">
        At <span className="fc-mono">{card.place.grid_ref ?? "this place"}</span>
      </p>
      <DetailStep
        meta={meta}
        visible={visible}
        status={sending || savingDraft ? "sending" : held ? "held" : "draft"}
        detail={detail}
        onDetail={useReviewStore.getState().setAnswer}
        revealing={revealing}
        onReveal={() => void showComparison(card, visible, detail)}
        focusOnMount={focus}
        onChangeAnswer={
          draft && !held && !ready
            ? () => {
                discardDraft(draft.id);
                useReviewStore.getState().setAnswer(null);
              }
            : undefined
        }
      />
    </div>
  );
}

function CardView({ meta, card }: { meta: Meta; card: ReviewCard }) {
  const reveal = useReviewStore((state) => state.reveal);
  const sending = useReviewStore((state) => state.sending);
  const held = useReviewStore((state) => state.held?.visible ?? null);
  const { ready } = useSession();
  const sheetDownThen = useSheetDownThen();
  const draft = useKindDrafts(answerDrafts).find((entry) => entry.data.public_id === card.public_id) ?? null;
  /** Set as an answer is given here: null until then, so a card coming back to its detail takes no focus. */
  const byKey = useRef<boolean | null>(null);
  // A draft is shown until it is saved: signed out, or ready and on its way. One that failed is answered afresh.
  const drafted = draft && (!ready || draft.state !== "failed") ? draft.data.answer.visible : null;
  const answering = reveal ? null : (sending ?? held ?? drafted);
  // While the person answers, the place stays in sight above the sheet.
  useAnswerInSight([card.place.lon, card.place.lat], answering === null ? null : `${card.public_id}:detail`);
  if (reveal) return <RevealCard meta={meta} reveal={reveal} onNext={sheetDownThen(useReviewStore.getState().next)} />;
  if (answering !== null) {
    const focus = byKey.current === null ? null : byKey.current ? "reveal" : "given";
    return <Detail meta={meta} card={card} visible={answering} draft={drafted ? draft : null} focus={focus} />;
  }
  return <Ask meta={meta} card={card} byKey={byKey} failed={draft?.state === "failed" ? draft : null} />;
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
