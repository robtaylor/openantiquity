/**
 * What each result of a scan is called. `/meta` has no words for survey
 * results, so they are written here, keyed by the schema's own union, and a
 * new result won't build until it has words.
 */

import type { SurveyResult } from "./api.js";

export const RESULT_WORDS: Record<SurveyResult, { button: string; recorded: string }> = {
  nothing: { button: "Nothing obvious", recorded: "nothing obvious" },
  marked: { button: "I marked something", recorded: "you marked something" },
  skipped: { button: "Skip this square", recorded: "skipped" },
};

/** "1 finding", "2 findings". */
export function findingsWords(count: number): string {
  return count === 1 ? "1 finding" : `${count} findings`;
}

/** "1 square", "3 squares". */
export function squaresWords(count: number): string {
  return count === 1 ? "1 square" : `${count} squares`;
}

/** How many people have looked a square over before, in a sentence. */
export function scansWords(scans: number): string {
  if (scans <= 0) return "Nobody has looked it over yet.";
  if (scans === 1) return "One person has looked it over so far.";
  return `${scans} people have looked it over so far.`;
}
