/**
 * A square scanned by someone not signed in is a draft in this browser
 * (Decision 0002, docs/UI.md "Behaviour"). Its data is the square and the
 * body `PUT /squares/{ref}` will be sent, so saving it after sign-in sends
 * exactly what was said. The saver is registered when this module loads,
 * which the shell does at start-up through `ScanLayer`, so a draft left
 * from before a provider's round trip is saved as soon as the person is
 * ready. A skip is never a draft: it says nothing about the square.
 */

import { isFiniteNumber, isRecord } from "../../api/guards.js";
import { defineDraftKind } from "../drafts/savers.js";
import { DRAFT_KINDS } from "../drafts/store.js";
import { squareWords } from "../findings/square.js";
import { putSurvey, type SurveyIn } from "./api.js";
import { RESULT_WORDS } from "./words.js";

export interface SquareDraftData {
  /** The compact reference, such as "SU1069". */
  square: string;
  survey: SurveyIn & { result: "nothing" | "marked" };
}

export function parseSquareDraft(value: unknown): SquareDraftData | null {
  if (!isRecord(value) || typeof value.square !== "string" || value.square === "") return null;
  const { survey } = value;
  if (!isRecord(survey) || (survey.result !== "nothing" && survey.result !== "marked")) return null;
  if (!isFiniteNumber(survey.findings_count)) return null;
  if (survey.seconds !== undefined && survey.seconds !== null && !isFiniteNumber(survey.seconds)) return null;
  return {
    square: value.square,
    survey: {
      result: survey.result,
      findings_count: survey.findings_count,
      ...(isFiniteNumber(survey.seconds) ? { seconds: survey.seconds } : {}),
    },
  };
}

export const squareDrafts = defineDraftKind<SquareDraftData>({
  kind: DRAFT_KINDS.square,
  label: "Scanned square",
  parse: parseSquareDraft,
  save: async (data) => {
    await putSurvey(data.square, data.survey);
  },
  describe: (data) => `${squareWords(data.square)}: ${RESULT_WORDS[data.survey.result].recorded}`,
});
