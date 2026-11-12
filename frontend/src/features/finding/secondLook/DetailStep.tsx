import { Eye, LogIn, Undo2 } from "lucide-react";
import { useEffect, useRef } from "react";
import type { Meta } from "../../../api/meta.js";
import { Button } from "../../../ui/Button.js";
import { DraftBadge } from "../../drafts/DraftBadge.js";
import type { Visible } from "../types.js";
import { AnswerDetail } from "./AnswerDetail.js";
import { ANSWER_WORDS, type AnswerDraft, detailBody, hasDetail } from "./answer.js";

/**
 * Where the answer stands while its detail is offered: on its way to the
 * server, in and counting, kept in this browser until sign-in, or given
 * before signing in and waiting for the person to say to send it.
 */
export type HeldStatus = "sending" | "held" | "draft" | "waiting";

export interface DetailStepProps {
  meta: Meta;
  /** The answer given, which can't change now (it can as a draft, from the answer buttons). */
  visible: Visible;
  status: HeldStatus;
  /** The detail as the person is giving it. */
  detail: AnswerDraft;
  onDetail: (detail: AnswerDraft) => void;
  /** Send the detail, or none, and see how the answer compares. For a draft: keep it and sign in. */
  onReveal: () => void;
  /** True while the reveal is on its way. */
  revealing: boolean;
  /** For an answer not sent yet, a draft: go back to the three answers. */
  onChangeAnswer?: () => void;
  /**
   * Where focus goes as the step appears, after the answer was pressed: the
   * line saying it is in, so the detail is read next, or, after an answer
   * given by its key, the button, so Enter shows the comparison.
   */
  focusOnMount?: "given" | "reveal" | null;
}

/** The status line above the detail. */
function statusLine(status: HeldStatus): string {
  switch (status) {
    case "sending":
      return "Sending your answer…";
    case "held":
      return "Your answer is in, and it counts.";
    case "draft":
      return "It's kept in this browser until you sign in.";
    case "waiting":
      return "It was given in this browser before you signed in, and hasn't been sent.";
  }
}

/**
 * The second step of a second look (Decision 0008): the answer is given, and
 * now the optional detail is offered, then one button that adds it, or
 * nothing, and shows how the answer compares. What the person adds here is
 * still unprompted, because nothing about the finder's claim or anyone
 * else's answer has been shown. Shared by the finding's page and the queue.
 */
export function DetailStep({
  meta,
  visible,
  status,
  detail,
  onDetail,
  onReveal,
  revealing,
  onChangeAnswer,
  focusOnMount = null,
}: DetailStepProps) {
  const givenLine = useRef<HTMLParagraphElement>(null);
  const bar = useRef<HTMLDivElement>(null);
  /** Focus still to be placed: the button can take it only once the answer is in. */
  const owed = useRef(focusOnMount);
  const ready = status !== "sending" && !revealing;
  useEffect(() => {
    if (owed.current === "given") givenLine.current?.focus({ preventScroll: true });
    else if (owed.current === "reveal" && ready) bar.current?.querySelector("button")?.focus({ preventScroll: true });
    else return;
    owed.current = null;
  }, [ready]);
  const added = hasDetail(detailBody(meta, detail));
  const label =
    status === "draft"
      ? "Sign in to see how it compares"
      : status === "waiting"
        ? "Send it and see how it compares"
        : revealing
          ? "Showing…"
          : added
            ? "Add this and see how it compares"
            : "See how it compares";
  return (
    <div className="fc-detail-step">
      <p className="fc-detail-step__given" role="status" tabIndex={-1} ref={givenLine}>
        <strong>{ANSWER_WORDS[visible].given}.</strong> {statusLine(status)}{" "}
        {status === "draft" || status === "waiting" ? <DraftBadge /> : null}
      </p>
      <AnswerDetail meta={meta} answer={detail} onChange={onDetail} />
      {/* Above the button, not in the bar that stays in sight, so on a half-open sheet the bar is the button alone
          and the detail has the room. */}
      <p className="fc-finding__hint">
        {status === "draft"
          ? "Signing in saves it all, then shows what the finder and others said."
          : status === "waiting"
            ? "An answer is final, so send it only if you gave it. Then you'll see what the finder and others said."
            : "Then you'll see what the finder and others said, and what you add is final."}
      </p>
      <div className="fc-second-look__send" ref={bar}>
        <Button
          variant="primary"
          block
          icon={status === "draft" ? <LogIn size={16} aria-hidden /> : <Eye size={16} aria-hidden />}
          disabled={!ready}
          onClick={onReveal}
        >
          {label}
        </Button>
        {onChangeAnswer ? (
          <Button size="sm" variant="ghost" icon={<Undo2 size={15} aria-hidden />} onClick={onChangeAnswer}>
            Change my answer
          </Button>
        ) : null}
      </div>
    </div>
  );
}

/**
 * Said above the answers when an answer kept as a draft failed to save after
 * sign-in: what went wrong, and that answering here sends a new one, which
 * replaces the draft.
 */
export function FailedDraftNotice({ message }: { message: string | undefined }) {
  return (
    <p className="fc-finding__inline-error" role="alert">
      The answer kept in this browser couldn't be saved. {message ?? "Something went wrong."} Answer again here to send
      it.
    </p>
  );
}
