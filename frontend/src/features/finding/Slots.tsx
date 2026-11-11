import type { ReportTarget } from "../reports/api.js";
import { ReportButton } from "../reports/ReportButton.js";
import type { FindingDetail } from "./types.js";

/**
 * Places on a finding's page that a later wave fills. Each is rendered where
 * its content belongs and draws nothing until it is built, so the page's
 * layout doesn't move when it arrives. The mentions and the follow-up
 * timeline, which had places here, are in `features/mentions/` and `timeline/`.
 */

export interface SlotProps {
  finding: FindingDetail;
}

/**
 * The report button, for a finding, a comment, a piece of evidence, a photo
 * or anything else on the page (DESIGN.md, "Protecting sites"). Nobody is
 * offered it on their own work.
 */
export function ReportSlot({
  target,
  ownerHandle,
  label,
}: {
  target: ReportTarget;
  ownerHandle: string | null;
  label?: string;
}) {
  return <ReportButton target={target} ownerHandle={ownerHandle} label={label} />;
}
