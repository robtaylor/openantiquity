/**
 * The two short notices the marking form carries. Both are worded here, but
 * the facts come from `/meta`: which classes start protected, and each
 * nation's reporting route for finds.
 */

import type { Meta } from "../../api/meta.js";

/**
 * Who will see exactly where a new finding of this class is, in one
 * sentence, or null for a class that starts open, or one `/meta` doesn't
 * say. Sensitivity is explained, never asked (Decision 0005): the finder
 * can raise it later from the finding's page.
 */
export function sensitivityNotice(meta: Meta, featureClass: string | null): string | null {
  const level = meta.vocab.feature_classes.find((candidate) => candidate.id === featureClass)?.default_sensitivity;
  if (level === "protected") {
    return "To protect sites like this, only signed-in members will see exactly where it is, and everyone else will see the one-kilometre square around it.";
  }
  if (level === "restricted") {
    return "To protect sites like this, only you, trusted members, archaeologists and moderators will see exactly where it is, and everyone else will see the one-kilometre square around it.";
  }
  return null;
}

/** The opening of the finds notice. The rest is the reporting route for where the mark is. */
export const FINDS_NOTICE =
  "This map is for earthworks, not objects. If you've found something in the ground, don't mark it here.";

/**
 * Where to report a find in this nation, from `/meta`: its own finds notice
 * once the backend sends one, otherwise the line of the nation's field-visit
 * notices that says to report a find. Null when neither is there, or the
 * nation isn't known.
 */
export function findsRoute(meta: Meta, nation: string | null): string | null {
  if (nation === null) return null;
  const own = meta.notices.finds?.[nation];
  if (own) return own;
  const lines = meta.notices.field_visit[nation] ?? [];
  return lines.find((line) => /report/i.test(line) && /\bfind|found\b/i.test(line)) ?? null;
}
