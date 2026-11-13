import { Undo2 } from "lucide-react";
import { useState } from "react";
import type { Meta } from "../../../api/meta.js";
import { Button } from "../../../ui/Button.js";
import { Dialog } from "../../../ui/Dialog.js";
import { Field } from "../../../ui/Field.js";
import { toast } from "../../../ui/toastStore.js";
import { putObservation, shapeRevisionField, withdrawObservation } from "../api.js";
import { classLabel } from "../describe.js";
import { toastFailure } from "../feedback.js";
import type { FindingDetail, Observation, Reveal } from "../types.js";
import { ANSWER_WORDS, isReveal, sameAnswer } from "./answer.js";

export interface GivenAnswerProps {
  meta: Meta;
  finding: FindingDetail;
  observation: Observation;
  /** The server's reply after a note is saved or an answer counted again. */
  onRevealed: (reveal: Reveal) => void;
  /** An answer never revealed, counted again: it waits for its detail once more. */
  onHeld: (observation: Observation) => void;
  /** After the answer is taken back: ask for the finding again. */
  onWithdrawn: () => void;
  /** The reveal above already says what the answer was, so it isn't said twice. */
  revealed?: boolean;
}

/**
 * Someone's own second look, once given. The answer itself is final
 * (Decision 0008), so only its note can be changed. It can be taken back,
 * which stops it counting, and then counted again as it was, but never
 * replaced by a different one.
 */
export function GivenAnswer({
  meta,
  finding,
  observation,
  onRevealed,
  onHeld,
  onWithdrawn,
  revealed = false,
}: GivenAnswerProps) {
  const [note, setNote] = useState(observation.note ?? "");
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const changed = note.trim() !== (observation.note ?? "").trim();

  async function send(body = sameAnswer(observation, note)): Promise<void> {
    setBusy(true);
    try {
      const reply = await putObservation(finding.public_id, {
        ...body,
        ...shapeRevisionField(finding.location.shape.revision),
      });
      if (isReveal(reply)) onRevealed(reply);
      else onHeld(reply.observation);
    } catch (error) {
      toastFailure("Your note couldn't be saved.", error);
    } finally {
      setBusy(false);
    }
  }

  async function withdraw(): Promise<void> {
    setConfirming(false);
    setBusy(true);
    try {
      await withdrawObservation(finding.public_id);
      toast("Your answer is taken back. It no longer counts.");
      onWithdrawn();
    } catch (error) {
      toastFailure("Your answer couldn't be taken back.", error);
    } finally {
      setBusy(false);
    }
  }

  const what = observation.feature_class ? ` (${classLabel(meta, observation.feature_class)})` : "";
  return (
    <div className="fc-given">
      <p>
        {revealed ? null : (
          <>
            <strong>{ANSWER_WORDS[observation.visible].given}</strong>
            {what}.{" "}
          </>
        )}
        {observation.withdrawn
          ? "You took this answer back, so it doesn't count."
          : "You can't change your answer. You can add a note, or take it back so it stops counting."}
      </p>
      {observation.withdrawn ? (
        <Button size="sm" disabled={busy} onClick={() => void send(sameAnswer(observation))}>
          Count it again
        </Button>
      ) : (
        <>
          <Field label="Your note" hint="Optional. What you saw, what you think it is, or which layer showed it best.">
            {(control) => (
              <textarea
                {...control}
                className="fc-input"
                rows={2}
                maxLength={5000}
                value={note}
                onChange={(event) => setNote(event.target.value)}
              />
            )}
          </Field>
          <div className="fc-given__actions">
            <Button size="sm" variant="primary" disabled={busy || !changed} onClick={() => void send()}>
              Save note
            </Button>
            <Button
              size="sm"
              variant="ghost"
              icon={<Undo2 size={15} aria-hidden />}
              disabled={busy}
              onClick={() => setConfirming(true)}
            >
              Take my answer back
            </Button>
          </div>
        </>
      )}
      <Dialog
        open={confirming}
        onClose={() => setConfirming(false)}
        title="Take your answer back?"
        actions={
          <>
            <Button onClick={() => setConfirming(false)}>Keep it</Button>
            <Button variant="danger" onClick={() => void withdraw()}>
              Take it back
            </Button>
          </>
        }
      >
        <p>
          It will stop counting towards this finding. You can count it again later, but not give a different answer.
        </p>
      </Dialog>
    </div>
  );
}
