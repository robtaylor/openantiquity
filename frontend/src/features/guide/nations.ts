/**
 * A nation's name from the id `/meta` keys its notices by, such as
 * "northern_ireland". `/meta` gives no names for them, so they are made from
 * the id.
 */
export function nationName(id: string): string {
  return id
    .split("_")
    .filter((word) => word !== "")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}
