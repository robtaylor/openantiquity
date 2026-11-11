/**
 * A title or description that says where a finding is more closely than its
 * one-kilometre square. The server refuses one on a finding that isn't open
 * (`position_in_text`, docs/ARCHITECTURE.md "Location sensitivity"), naming
 * each field in the error's details, so the form can say it beside that
 * field. What counts as a position is the server's to decide: the client
 * only shows the refusal. For people who may not see the exact place, the
 * server sends such text with each position replaced by a placeholder, which
 * the page shows as it comes.
 */

import { ApiError } from "../../api/client.js";

export const POSITION_IN_TEXT = "position_in_text";

/** The free-text fields of a finding that the refusal can name. */
export type PositionField = "title" | "description";

/** Which of the finding's fields a refusal names, or none when it is another refusal. */
export function positionFields(error: unknown): ReadonlySet<PositionField> {
  if (!(error instanceof ApiError) || error.code !== POSITION_IN_TEXT) return new Set();
  return namedFields(error.fields.map((problem) => problem.field));
}

/**
 * The finding's fields among a `position_in_text` refusal's, such as
 * `body.title`, kept with a draft that failed to save for it. A refusal that
 * names nothing it can be placed by is about both.
 */
export function namedFields(fields: readonly string[]): ReadonlySet<PositionField> {
  const named = new Set<PositionField>();
  for (const field of fields) {
    if (field === "body.title") named.add("title");
    if (field === "body.description") named.add("description");
  }
  return named.size > 0 ? named : new Set<PositionField>(["title", "description"]);
}

/** What to say beside the field, in plain words that say what to do. */
export function positionWords(field: PositionField): string {
  // The description is called the note on every form.
  const noun = field === "title" ? "title" : "note";
  return `Take the grid reference, coordinates or three-word address out of the ${noun}. This finding's exact place is kept back to protect the site, so its ${noun} can say no more than its one-kilometre square.`;
}
