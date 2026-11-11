/**
 * The order of a notebook's items. The server takes a move as "put this
 * item straight after that one, or first", so a move worked out here
 * carries the new order to show at once and the item it now follows.
 */

export interface Moved<T> {
  items: T[];
  /** The id of the item the moved one now follows, or null when it is first. */
  after: number | null;
}

/** `id` moved to place `to` (counted from 0, in the new order), or null when nothing would change. */
export function moveTo<T extends { id: number }>(items: readonly T[], id: number, to: number): Moved<T> | null {
  const from = items.findIndex((item) => item.id === id);
  if (from < 0 || to < 0 || to >= items.length || to === from) return null;
  const rest = items.filter((item) => item.id !== id);
  const moving = items[from] as T;
  rest.splice(to, 0, moving);
  return { items: rest, after: to === 0 ? null : (rest[to - 1] as T).id };
}

/**
 * The place an item dragged from `from` takes when it is dropped on the
 * item at `over`, on its upper or lower half. Places count in the order
 * once the dragged item has left its own.
 */
export function dropIndex(from: number, over: number, side: "before" | "after"): number {
  const target = side === "before" ? over : over + 1;
  return target > from ? target - 1 : target;
}
