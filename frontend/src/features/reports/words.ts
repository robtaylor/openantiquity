/**
 * The words around a report: what each kind of target is called, what the
 * reporter is told once it is sent, and why one was refused. `/meta` gives
 * the reasons themselves (`vocab.report_reasons`); it has no words for
 * these, so they are written here, typed over every target kind.
 */

import { ApiError } from "../../api/client.js";
import type { ReportReason } from "../../api/meta.js";
import type { ReportTargetKind } from "./api.js";

/** "this comment", for the button's name and the dialog's title. */
export const TARGET_WORDS: Record<ReportTargetKind, string> = {
  finding: "this finding",
  comment: "this comment",
  evidence: "this evidence",
  mention: "this mention",
  photo: "this photo",
  user: "this person",
  investigation: "this investigation",
};

/** What happens next, said once the report is in. A reporter is told nothing more later (Decision 0009). */
export function afterReport(kind: ReportTargetKind, reason: ReportReason | undefined): string[] {
  const when =
    reason?.due_hours != null
      ? `A moderator will look at it within ${reason.due_hours} hours, as the law asks for a report like this.`
      : "A moderator will look at it.";
  const person = kind === "user";
  return [
    when,
    person
      ? "If they break the rules, a moderator will act on it. You won't hear back about what they decide."
      : "If it breaks the rules, they'll hide it or take other action. You won't hear back about what they decide.",
    person ? "They aren't told who reported them." : "Whoever posted it isn't told who reported it.",
  ];
}

/** Why a report wasn't taken, in plain words where the code is known. */
export function reportProblem(error: unknown): string {
  if (error instanceof ApiError) {
    switch (error.code) {
      case "already_reported":
        return "You've already reported this, and the moderators haven't looked at it yet. There's no need to send it again.";
      case "recently_dismissed":
        return "A moderator has just looked at your report on this. You can report it again tomorrow.";
      case "cannot_report_self":
        return "You can't report yourself.";
      case "target_not_found":
        return "It isn't there any more, or you can't see it.";
      case "rate_limited":
        return "You've sent a lot of reports in the last hour. Try again later.";
    }
    if (error.status === 0 || error.status >= 500) return `${error.message} Try again in a moment.`;
    return error.message;
  }
  return "The report couldn't be sent.";
}
