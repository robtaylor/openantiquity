import { LogIn, Send } from "lucide-react";
import { type ReactNode, type Ref, useEffect, useRef, useState } from "react";
import type { Meta } from "../../../api/meta.js";
import { Button } from "../../../ui/Button.js";
import { toast } from "../../../ui/toastStore.js";
import { DraftBadge } from "../../drafts/DraftBadge.js";
import { useKindDrafts } from "../../drafts/savers.js";
import { DraftBusyError, DraftTooLargeError } from "../../drafts/store.js";
import { putObservation } from "../api.js";
import type { ViewerPosition } from "../describe.js";
import { reasonOf, useSignedInFirst } from "../feedback.js";
import type { FindingDetail, Reveal, Visible } from "../types.js";
import { AnswerButtons } from "./AnswerButtons.js";
import { AnswerDetail } from "./AnswerDetail.js";
import { ANSWER_WORDS, type AnswerDraft, answerBody, newAnswer } from "./answer.js";
import { answerDrafts, useSavedAnswers } from "./answerDrafts.js";
import { GivenAnswer } from "./GivenAnswer.js";
import { RevealSummary } from "./RevealSummary.js";

export interface SecondLookProps {
  meta: Meta;
  finding: FindingDetail;
  position: ViewerPosition;
  /** Signed in and through the welcome step. */
  ready: boolean;
  /** The finding as the answer revealed it. */
  onRevealed: (reveal: Reveal) => void;
  /** Ask for the finding again, after an answer is taken back. */
  onRefresh: () => void;
  ref?: Ref<HTMLElement>;
}

/** What someone who hasn't answered sees before they do: the answers, and what giving one means. */
function Ask({ meta, finding, ready, onRevealed }: Pick<SecondLookProps, "meta" | "finding" | "ready" | "onRevealed">) {
  const signedIn = useSignedInFirst();
  const [answer, setAnswer] = useState<AnswerDraft | null>(null);
  const [sending, setSending] = useState(false);

  function choose(visible: Visible): void {
    setAnswer((current) => (current ? { ...current, visible } : newAnswer(visible)));
  }

  async function keepAsDraft(chosen: AnswerDraft): Promise<void> {
    try {
      answerDrafts.put({ public_id: finding.public_id, answer: answerBody(meta, chosen) });
    } catch (error) {
      if (error instanceof DraftTooLargeError || error instanceof DraftBusyError) {
        toast(error.message, { kind: "error" });
        return;
      }
      throw error;
    }
    if (!(await signedIn())) {
      toast("Your answer is kept in this browser. Sign in when you're ready, and it will be saved.");
    }
  }

  async function send(chosen: AnswerDraft): Promise<void> {
    if (!ready) {
      await keepAsDraft(chosen);
      return;
    }
    setSending(true);
    try {
      onRevealed(await putObservation(finding.public_id, answerBody(meta, chosen)));
    } catch (error) {
      setSending(false);
      toast(`Your answer couldn't be sent. ${reasonOf(error)}`, {
        kind: "error",
        duration: 0,
        action: { label: "Try again", onClick: () => void send(chosen) },
      });
    }
  }

  return (
    <>
      <p className="fc-finding__hint">
        Look at the map in the finder's view, then say whether you can see a feature there. Other people's answers stay
        hidden until you've given yours, and your answer is final once sent.
      </p>
      <AnswerButtons value={answer?.visible ?? null} onChoose={choose} disabled={sending} />
      {answer ? (
        <>
          <AnswerDetail meta={meta} answer={answer} onChange={setAnswer} />
          <div className="fc-second-look__send">
            <Button
              variant="primary"
              block
              icon={<Send size={16} aria-hidden />}
              disabled={sending}
              onClick={() => void send(answer)}
            >
              {sending ? "Sending…" : `Send: ${ANSWER_WORDS[answer.visible].button.toLowerCase()}`}
            </Button>
          </div>
        </>
      ) : null}
    </>
  );
}

/**
 * The second look on a finding's page, for anyone who isn't its finder and
 * can see its exact place (Decision 0008). Before an answer: the three
 * answers, then the optional detail, then one button to send. After: how it
 * compares, and the person's own answer, whose note can still change and
 * which can be taken back. A signed-out person's answer is a draft until
 * they sign in. Built to be reused by the blind queue.
 */
export function SecondLook({ meta, finding, position, ready, onRevealed, onRefresh, ref }: SecondLookProps) {
  const [reveal, setReveal] = useState<Reveal | null>(null);
  const drafts = useKindDrafts(answerDrafts);
  const draft = drafts.find((entry) => entry.data.public_id === finding.public_id) ?? null;
  const signedIn = useSignedInFirst();
  const saved = useSavedAnswers((state) => state.revealed[finding.public_id]);

  // A draft saved after sign-in reveals the finding as a sent answer does, once.
  const applied = useRef<Reveal | null>(null);
  useEffect(() => {
    if (!saved || applied.current === saved) return;
    applied.current = saved;
    setReveal(saved);
    onRevealed(saved);
  }, [saved, onRevealed]);

  const shown = reveal?.finding.public_id === finding.public_id ? reveal : null;
  const observation = finding.my_observation;
  if (!observation && !position.mayAnswer && !draft) return null;

  let body: ReactNode;
  if (observation) {
    body = (
      <>
        {shown ? <RevealSummary meta={meta} reveal={shown} /> : null}
        <GivenAnswer
          key={`${observation.updated_at}-${observation.withdrawn}`}
          meta={meta}
          finding={finding}
          observation={observation}
          onRevealed={(next) => {
            setReveal(next);
            onRevealed(next);
          }}
          onWithdrawn={onRefresh}
        />
      </>
    );
  } else if (draft) {
    body = (
      <div className="fc-given">
        <p>
          <strong>{ANSWER_WORDS[draft.data.answer.visible].given}.</strong> <DraftBadge />
        </p>
        <p className="fc-finding__hint">
          It's kept in this browser until you sign in. Then it's saved, and you'll see what others said.
        </p>
        <Button size="sm" variant="primary" icon={<LogIn size={15} aria-hidden />} onClick={() => void signedIn()}>
          Sign in to save it
        </Button>
      </div>
    );
  } else {
    body = (
      <Ask
        meta={meta}
        finding={finding}
        ready={ready}
        onRevealed={(next) => {
          setReveal(next);
          onRevealed(next);
        }}
      />
    );
  }

  return (
    <section
      className="fc-finding__section fc-second-look"
      aria-labelledby="fc-second-look-title"
      ref={ref}
      tabIndex={-1}
    >
      <h3 id="fc-second-look-title">Your second look</h3>
      {body}
    </section>
  );
}
