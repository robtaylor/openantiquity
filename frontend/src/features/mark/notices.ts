/**
 * The two short notices the marking form carries. Both are worded here, but
 * the facts come from `/meta`: which classes start protected, and each
 * nation's reporting route for finds.
 */

import type { FindReporting, Meta } from "../../api/meta.js";

/**
 * Who will see exactly where a new finding of this class is, in one
 * sentence, or null for a class that starts open, or one `/meta` doesn't
 * say. Sensitivity is explained, never asked (Decision 0005): the finder
 * can protect an open finding later from the finding's page.
 */
export function sensitivityNotice(meta: Meta, featureClass: string | null): string | null {
  const level = meta.vocab.feature_classes.find((candidate) => candidate.id === featureClass)?.sensitivity;
  if (level === "protected") {
    return "To protect sites like this, only signed-in members will see exactly where it is, and everyone else will see the one-kilometre square around it.";
  }
  return null;
}

/** The opening of the finds notice. The rest is the reporting route for where the mark is. */
export const FINDS_NOTICE =
  "This map is for earthworks, not objects. If you've found something in the ground, don't mark it here.";

/**
 * Where to report a find in this nation, from `/meta`, or null when the
 * nation isn't known.
 */
export function findsRoute(meta: Meta, nation: string | null): FindReporting | null {
  return nation === null ? null : (meta.notices.find_reporting[nation] ?? null);
}
