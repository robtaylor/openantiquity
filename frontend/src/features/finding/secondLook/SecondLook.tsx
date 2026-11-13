import { type ReactNode, type Ref, useEffect, useRef, useState } from "react";
import type { Meta } from "../../../api/meta.js";
import { toast } from "../../../ui/toastStore.js";
import { accountIdentity, useSession } from "../../account/session.js";
import { useKindDrafts } from "../../drafts/savers.js";
import { discardDraft, sendHeldDraft } from "../../drafts/store.js";
import { giveAnswer, isShapeChanged, revealAsAsked, SHAPE_CHANGED_WORDS } from "../api.js";
import type { ViewerPosition } from "../describe.js";
import { toastFailureWithRetry, useSignedInFirst } from "../feedback.js";
import type { FindingDetail, Observation, Reveal, Visible } from "../types.js";
import { AnswerButtons } from "./AnswerButtons.js";
import {
  ALREADY_FINISHED,
  type AnswerDraft,
  answerBody,
  answerFromBody,
  detailBody,
  isReveal,
  newAnswer,
} from "./answer.js";
import {
  answerDrafts,
  discardAnswerDrafts,
  keepAnswerDraft,
  savedAnswerCount,
  useSavedAnswers,
} from "./answerDrafts.js";
import { DetailStep, FailedDraftNotice } from "./DetailStep.js";
import { GivenAnswer } from "./GivenAnswer.js";
import { RevealSummary } from "./RevealSummary.js";
import { useAnswerInSight } from "./useAnswerInSight.js";

export interface SecondLookProps {
  meta: Meta;
  finding: FindingDetail;
  position: ViewerPosition;
  /** Signed in and through the welcome step. */
  ready: boolean;
  /** The finding as the answer revealed it. */
  onRevealed: (reveal: Reveal) => void;
  /** The answer is in and waits for its detail: the page holds it as the server's own answer. */
  onHeld: (observation: Observation) => void;
  /** Ask for the finding again, after an answer is taken back. */
  onRefresh: () => void;
  ref?: Ref<HTMLElement>;
}

/**
 * A second look on the page, in two steps (Decision 0008, docs/UI.md
 * "Behaviour"). The answer is one press, sent at once and shown at once. The
 * optional detail is offered after it, with one button that adds it, or
 * nothing, and shows how the answer compares. Someone who leaves between
 * the two finds the detail offered again, because the server says their
 * answer waits for it (`my_observation.revealed` false). Signed out, the
 * answer and its detail are a draft, sent in that order after sign-in.
 */
export function SecondLook({ meta, finding, position, ready, onRevealed, onHeld, onRefresh, ref }: SecondLookProps) {
  const { public_id: publicId } = finding;
  const [reveal, setReveal] = useState<Reveal | null>(null);
  /** An answer pressed and on its way, shown at once, until the server has it. */
  const [sending, setSending] = useState<Visible | null>(null);
  const [detail, setDetail] = useState<AnswerDraft | null>(null);
  const [revealing, setRevealing] = useState(false);
  /** True after an answer was refused because the shape changed while the person looked. */
  const [shapeChanged, setShapeChanged] = useState(false);
  const revision = finding.location.shape.revision;
  const drafts = useKindDrafts(answerDrafts);
  const draft = drafts.find((entry) => entry.data.public_id === publicId) ?? null;
  const signedIn = useSignedInFirst();
  const { me } = useSession();
  const account = me ? accountIdentity(me) : null;
  const [openedAfter] = useState(savedAnswerCount);
  const saved = useSavedAnswers((state) => state.saved[publicId]);

  // A draft saved after sign-in, while this page is open: its reveal is shown once, or its detail is offered.
  // The page asks for the finding again rather than taking the reply's copy, which may be older than its own.
  useEffect(() => {
    if (!saved) return;
    useSavedAnswers.getState().forget(publicId);
    if (saved.kind === "revealed" && saved.seq > openedAfter) setReveal(saved.reveal);
    onRefresh();
  }, [saved, openedAfter, publicId, onRefresh]);

  const shown = reveal?.finding.public_id === publicId ? reveal : null;
  const observation = finding.my_observation;
  const heldVisible = sending ?? (position.answerHeld ? (observation?.visible ?? null) : null);
  // A draft is shown until it is saved: signed out, or ready and on its way. One that failed is answered afresh.
  const draftVisible = draft && (!ready || draft.state !== "failed") ? draft.data.answer.visible : null;
  const answering = heldVisible ?? draftVisible;
  const heading = useRef<HTMLHeadingElement>(null);
  const revealed = shown !== null;
  // The reveal starts under the section's heading, on a half-open sheet too, whatever the detail before it was
  // scrolled to. The button pressed for it has gone with the detail, so focus, if it was lost or was in here,
  // goes to the heading and the next Tab carries on from the reveal.
  useEffect(() => {
    const target = heading.current;
    if (!revealed || !target) return;
    target.scrollIntoView?.({ block: "start" });
    const active = document.activeElement;
    if (active === null || active === document.body || target.parentElement?.contains(active)) {
      target.focus({ preventScroll: true });
    }
  }, [revealed]);
  // While the detail is asked, the place stays in sight above the sheet.
  useAnswerInSight(
    finding.location.obscured ? null : [finding.location.lon, finding.location.lat],
    answering === null || revealed ? null : `${publicId}:detail`,
  );

  function done(next: Reveal): void {
    setReveal(next);
    setDetail(null);
    onRevealed(next);
  }

  /** True once an answer was pressed here, so the detail that follows takes focus. */
  const pressed = useRef(false);

  async function answer(visible: Visible): Promise<void> {
    pressed.current = true;
    setShapeChanged(false);
    if (!ready) {
      const data = { public_id: publicId, answer: { visible }, reveal: false, shape_revision: revision };
      const kept = keepAnswerDraft(data, draft?.id);
      if (kept) setDetail(newAnswer(visible));
      return;
    }
    setSending(visible);
    setDetail(newAnswer(visible));
    try {
      const reply = await giveAnswer(publicId, visible, revision);
      // A draft of an earlier answer that failed to save is done with: this answer is the one that counts.
      discardAnswerDrafts(publicId);
      if (isReveal(reply)) done(reply);
      else onHeld(reply.observation);
    } catch (error) {
      setDetail(null);
      if (isShapeChanged(error)) {
        // Nothing was stored. The page asks for the finding again, and the answer is given afresh on what it is now.
        setShapeChanged(true);
        onRefresh();
        return;
      }
      toastFailureWithRetry("Your answer couldn't be sent.", error, () => void answer(visible));
    } finally {
      setSending(null);
    }
  }

  async function showComparison(visible: Visible, given: AnswerDraft): Promise<void> {
    if (ready && draft?.held && account !== null) {
      // Given here before signing in: the person now says it is theirs, with the detail as it stands.
      const data = {
        public_id: publicId,
        answer: answerBody(meta, { ...given, visible }),
        reveal: true,
        shape_revision: draft.data.shape_revision ?? revision,
      };
      if (keepAnswerDraft(data, draft.id)) sendHeldDraft(draft.id, account);
      return;
    }
    if (!ready) {
      const data = {
        public_id: publicId,
        answer: answerBody(meta, { ...given, visible }),
        reveal: true,
        shape_revision: draft?.data.shape_revision ?? revision,
      };
      if (keepAnswerDraft(data, draft?.id) && !(await signedIn())) {
        toast("Your answer is kept in this browser until you sign in.");
      }
      return;
    }
    setRevealing(true);
    try {
      done(await revealAsAsked(publicId, detailBody(meta, { ...given, visible }), () => toast(ALREADY_FINISHED)));
    } catch (error) {
      toastFailureWithRetry("It couldn't be shown.", error, () => void showComparison(visible, given));
    } finally {
      setRevealing(false);
    }
  }

  if (!observation && !shown && !position.mayAnswer && !draft && sending === null) return null;

  let body: ReactNode;
  if (shown && !observation) {
    // Saved from a draft: the page is asking for the finding again. The reveal above is all there is to show.
    body = null;
  } else if (answering !== null) {
    const given = detail ?? (draft && draftVisible !== null ? answerFromBody(meta, draft.data.answer) : null);
    body = (
      <DetailStep
        meta={meta}
        visible={answering}
        // A draft of someone now ready is on its way through the drafts machinery.
        status={
          sending !== null
            ? "sending"
            : heldVisible !== null
              ? "held"
              : !ready
                ? "draft"
                : draft?.held
                  ? "waiting"
                  : "sending"
        }
        detail={given ?? newAnswer(answering)}
        onDetail={setDetail}
        focusOnMount={pressed.current ? "given" : null}
        revealing={revealing || draft?.state === "saving"}
        onReveal={() => void showComparison(answering, given ?? newAnswer(answering))}
        onChangeAnswer={
          draft && heldVisible === null && (!ready || draft.held)
            ? () => {
                discardDraft(draft.id);
                setDetail(null);
              }
            : undefined
        }
      />
    );
  } else if (observation) {
    body = (
      <GivenAnswer
        key={`${observation.updated_at}-${observation.withdrawn}`}
        meta={meta}
        finding={finding}
        observation={observation}
        revealed={revealed}
        onRevealed={done}
        onHeld={onHeld}
        onWithdrawn={onRefresh}
      />
    );
  } else {
    body = (
      <>
        <p className="fc-finding__hint">
          Look at the map in the finder's view, then say whether you can see a feature there. Your answer counts as soon
          as you give it. Other people's answers stay hidden until you've had a chance to say more.
        </p>
        {draft?.state === "failed" ? <FailedDraftNotice message={draft.failure?.message} /> : null}
        <AnswerButtons value={null} onChoose={(visible) => void answer(visible)} />
      </>
    );
  }

  return (
    <section
      className="fc-finding__section fc-second-look"
      aria-labelledby="fc-second-look-title"
      ref={ref}
      tabIndex={-1}
    >
      <h3 id="fc-second-look-title" className="fc-second-look__title" tabIndex={-1} ref={heading}>
        Your second look
      </h3>
      {/* There before the answer, so the reveal is read out when it arrives. */}
      <div className="fc-second-look__news" role="status">
        {shown ? <RevealSummary meta={meta} reveal={shown} /> : null}
        {shapeChanged && !shown ? <p className="fc-finding__notice">{SHAPE_CHANGED_WORDS}</p> : null}
      </div>
      {body}
    </section>
  );
}
