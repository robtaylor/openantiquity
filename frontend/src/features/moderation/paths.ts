/**
 * The addresses of moderation's pages, apart from the panels, so a
 * notification or a finding's page can link to them without loading them.
 */

export const MOD_PATH = "/mod";
export const MOD_ROUTE = `${MOD_PATH}/:section?`;

/** The admins' list of markings whose keeper's account is deleted or banned. */
export const MARKINGS_PATH = `${MOD_PATH}/markings`;

/** An admin's removal of one orphaned marking. */
export const REMOVE_MARKING_ROUTE = `${MARKINGS_PATH}/:publicId`;

export function removeMarkingPath(publicId: string): string {
  return `${MARKINGS_PATH}/${encodeURIComponent(publicId)}`;
}
