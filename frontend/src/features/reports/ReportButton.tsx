import { Flag } from "lucide-react";
import { useId, useState } from "react";
import { useMeta } from "../../api/useMeta.js";
import { Button, type ButtonSize } from "../../ui/Button.js";
import { Dialog } from "../../ui/Dialog.js";
import { Field } from "../../ui/Field.js";
import { useSession } from "../account/session.js";
import { useSignedInFirst } from "../finding/feedback.js";
import { type ReportReasonId, type ReportTarget, sendReport } from "./api.js";
import { afterReport, reportProblem, TARGET_WORDS } from "./words.js";
import "./reports.css";

const NOTE_MAX = 2000;

function ReportDialog({ target, onClose }: { target: ReportTarget; onClose: () => void }) {
  const meta = useMeta();
  const reasons = meta.data?.vocab.report_reasons ?? [];
  const [reason, setReason] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const legendId = useId();
  const what = TARGET_WORDS[target.kind];
  const chosen = reasons.find((entry) => entry.id === reason);

  async function send(): Promise<void> {
    if (reason === null) {
      setProblem("Choose what's wrong first.");
      return;
    }
    setSending(true);
    setProblem(null);
    try {
      await sendReport(target, reason as ReportReasonId, note.trim() || null);
      setSent(true);
    } catch (error) {
      setProblem(reportProblem(error));
    } finally {
      setSending(false);
    }
  }

  return (
    <Dialog
      open
      onClose={onClose}
      title={sent ? "Thanks, your report is in" : `Report ${what}`}
      actions={
        sent ? (
          <Button variant="primary" onClick={onClose}>
            Done
          </Button>
        ) : (
          <>
            <Button onClick={onClose}>Cancel</Button>
            <Button variant="primary" disabled={sending} onClick={() => void send()}>
              {sending ? "Sending…" : "Send report"}
            </Button>
          </>
        )
      }
    >
      {/* The same live region holds the form's place, so the confirmation is read out when it replaces it. */}
      <div role="status" className="fc-report__after">
        {sent ? afterReport(target.kind, chosen).map((line) => <p key={line}>{line}</p>) : null}
      </div>
      {sent ? null : (
        <form
          className="fc-report"
          onSubmit={(event) => {
            event.preventDefault();
            void send();
          }}
        >
          <fieldset className="fc-report__reasons" aria-labelledby={legendId}>
            <legend id={legendId} className="fc-field__label">
              What's wrong with it?
            </legend>
            {reasons.map((entry) => (
              <label key={entry.id} className="fc-report__reason">
                <input
                  type="radio"
                  name="report-reason"
                  value={entry.id}
                  checked={reason === entry.id}
                  onChange={() => {
                    setReason(entry.id);
                    setProblem(null);
                  }}
                />
                <span>
                  <span className="fc-report__reason-label">{entry.label}</span>
                  <span className="fc-report__reason-hint">{entry.hint}</span>
                </span>
              </label>
            ))}
          </fieldset>
          <Field label="Anything the moderators should know (optional)" hint="Only moderators read this.">
            {(control) => (
              <textarea
                {...control}
                className="fc-input"
                rows={3}
                maxLength={NOTE_MAX}
                value={note}
                onChange={(event) => setNote(event.target.value)}
              />
            )}
          </Field>
          {problem ? (
            <p className="fc-field__error" role="alert">
              {problem}
            </p>
          ) : null}
        </form>
      )}
    </Dialog>
  );
}

export interface ReportButtonProps {
  target: ReportTarget;
  /** Who posted it, by handle. Nobody is offered a report on their own work, or on themselves. */
  ownerHandle?: string | null;
  size?: ButtonSize;
  /** The words on the button, where "Report" alone wouldn't say which of two things it reports. */
  label?: string;
}

/**
 * "Report", on anything someone else posted (DESIGN.md, "Protecting sites").
 * A signed-out person is asked to sign in first. The dialog asks for a
 * reason from `/meta` and an optional note, and then says plainly what
 * happens next.
 */
export function ReportButton({ target, ownerHandle = null, size = "sm", label = "Report" }: ReportButtonProps) {
  const session = useSession();
  const signedInFirst = useSignedInFirst();
  const [open, setOpen] = useState(false);
  const mine = session.me !== null && ownerHandle !== null && session.me.handle === ownerHandle;
  if (mine) return null;
  return (
    <>
      <Button
        size={size}
        variant="ghost"
        icon={<Flag size={14} aria-hidden />}
        aria-label={`Report ${TARGET_WORDS[target.kind]}`}
        onClick={() => {
          void signedInFirst().then((ready) => {
            if (ready) setOpen(true);
          });
        }}
      >
        {label}
      </Button>
      {open ? <ReportDialog target={target} onClose={() => setOpen(false)} /> : null}
    </>
  );
}
