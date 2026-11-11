/**
 * A link to a finding's page that opens it ready to do one of its next
 * steps: help wanted sends people here with the form for the work they
 * chose already open. The step is named by its code, and a step that wants
 * a kind of evidence by its strand too, such as `historic_map`. The page
 * works out the form from its own next steps, so a step met since the link
 * was made opens nothing.
 */

import type { Meta } from "../../api/meta.js";
import { findingPath } from "../findings/selection.js";
import { type StepAction, stepActions, type ViewerPosition } from "./describe.js";
import type { FindingDetail } from "./types.js";

export const STEP_PARAM = "step";
export const STRAND_PARAM = "strand";

export interface StepRequest {
  code: string;
  strand: string | null;
}

export function findingStepPath(publicId: string, code: string, strand: string | null = null): string {
  const query = new URLSearchParams({ [STEP_PARAM]: code });
  if (strand) query.set(STRAND_PARAM, strand);
  return `${findingPath(publicId)}?${query.toString()}`;
}

export function stepFromAddress(params: URLSearchParams): StepRequest | null {
  const code = params.get(STEP_PARAM);
  return code ? { code, strand: params.get(STRAND_PARAM) } : null;
}

/** The button the page would offer for that step, for this viewer: the strand's form if one is named. */
export function actionForStep(
  finding: FindingDetail,
  meta: Meta,
  position: ViewerPosition,
  request: StepRequest,
): StepAction | null {
  const step = finding.assessment.next_steps.find((each) => each.code === request.code);
  if (!step) return null;
  const actions = stepActions(step, meta, position).filter((action) => action.kind !== "share");
  if (request.strand !== null) {
    const strandOf = (kindId: string) => meta.vocab.evidence_kinds.find((kind) => kind.id === kindId)?.strand;
    const wanted = actions.find(
      (action) => action.kind === "evidence" && strandOf(action.evidenceKind) === request.strand,
    );
    if (wanted) return wanted;
  }
  return actions[0] ?? null;
}
