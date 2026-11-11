import type { FindingDetail } from "./types.js";

/**
 * Places on a finding's page that a later wave fills. Each is rendered where
 * its content belongs and draws nothing yet, so the page's layout doesn't
 * move when it arrives. The mentions and the follow-up timeline, which had
 * places here, are in `features/mentions/` and `timeline/`.
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
