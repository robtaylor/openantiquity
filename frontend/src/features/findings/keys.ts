/**
 * Every query key for findings, in one place. Each starts with "findings",
 * so `findingKeys.all` invalidates them all, which is what a save does: the
 * map, the list and any open page then ask again.
 *
 * What the server sends depends on who is asking (Decision 0005). None of
 * these keys is viewer-independent, so the session drops them all when the
 * person changes.
 */

export const findingKeys = {
  all: ["findings"] as const,
  /** The map's GeoJSON for a snapped box, with the filters, and the overlay's retry count. */
  box: (bbox: string | null, filters: string, attempt: number) => ["findings", "bbox", bbox, filters, attempt] as const,
  /** The Explore list's pages for a snapped box and the filters. */
  list: (bbox: string | null, filters: string) => ["findings", "list", bbox, filters] as const,
  /** One finding's page. */
  detail: (publicId: string) => ["findings", "detail", publicId] as const,
};
