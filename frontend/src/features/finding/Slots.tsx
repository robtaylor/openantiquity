import type { FindingDetail } from "./types.js";

/**
 * Places on a finding's page that a later wave fills. Each is rendered where
 * its content belongs and draws nothing yet, so the page's layout doesn't
 * move when it arrives.
 */

export interface SlotProps {
  finding: FindingDetail;
}

/** The report button, for a finding, a comment or a piece of evidence (DESIGN.md, "Protecting sites"). */
export function ReportSlot(
  _props: SlotProps & { target?: { kind: "finding" | "comment" | "evidence"; id: string | number } },
) {
  return null;
}

/** Videos, articles, podcasts and papers that mention the finding (DESIGN.md, "Mentions and follow-ups"). */
export function MentionsSlot(_props: SlotProps) {
  return null;
}

/** Dated site visits, surveys, digs and new records, as a timeline (DESIGN.md, "Mentions and follow-ups"). */
export function FollowUpTimelineSlot(_props: SlotProps) {
  return null;
}
