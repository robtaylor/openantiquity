import { type ReactNode, useState } from "react";
import { Button } from "../../ui/Button.js";
import { Dialog } from "../../ui/Dialog.js";
import { Field } from "../../ui/Field.js";
import "./moderation.css";

/** The longest reason the server keeps for the log. */
export const REASON_MAX = 1000;

export interface ReasonDialogProps {
  title: string;
  /** What this will do, said before the reason is asked for. */
  children?: ReactNode;
  confirmLabel: string;
  /** For an action that takes something away from someone: hiding, refusing, banning. */
  danger?: boolean;
  label?: string;
  hint?: string;
  /** Whether the action can go ahead with what else the dialog asks, beside the reason. */
  ready?: boolean;
  /** Called with the reason, already trimmed. The dialog closes at once: the caller shows the change and puts it back if refused. */
  onConfirm: (reason: string) => void;
  onClose: () => void;
}

/**
 * Asks for the reason every moderation action needs for the log, and goes
 * ahead only once one is given. It closes as soon as it is confirmed: what
 * it does shows at once and is put back with a toast if the server refuses.
 */
export function ReasonDialog({
  title,
  children,
  confirmLabel,
  danger = false,
  label = "Why",
  hint = "This goes in the moderation log, which only moderators read.",
  ready = true,
  onConfirm,
  onClose,
}: ReasonDialogProps) {
  const [reason, setReason] = useState("");
  const [problem, setProblem] = useState<string | null>(null);

  function confirm(): void {
    const given = reason.trim();
    if (!given) {
      setProblem("Say why, for the log.");
      return;
    }
    onConfirm(given);
    onClose();
  }

  return (
    <Dialog
      open
      onClose={onClose}
      title={title}
      actions={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant={danger ? "danger" : "primary"} disabled={!ready} onClick={confirm}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <form
        className="fc-mod-dialog"
        onSubmit={(event) => {
          event.preventDefault();
          confirm();
        }}
      >
        {children}
        <Field label={label} hint={hint} error={problem ?? undefined}>
          {(control) => (
            <textarea
              {...control}
              className="fc-input"
              rows={3}
              maxLength={REASON_MAX}
              value={reason}
              onChange={(event) => {
                setReason(event.target.value);
                setProblem(null);
              }}
            />
          )}
        </Field>
      </form>
    </Dialog>
  );
}
