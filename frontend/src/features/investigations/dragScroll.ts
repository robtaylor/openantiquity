/**
 * Scrolling the panel or the sheet while an item is dragged near its edge,
 * so an item can be dragged further than one screen of the list.
 */

/** How near the top or bottom edge, in pixels, the pointer starts the scroll. */
export const EDGE_PX = 40;
/** The fastest it scrolls, in pixels a frame, with the pointer on the edge or past it. */
export const MAX_STEP_PX = 14;

/** How far to scroll this frame for a pointer at `y`: up is negative, and nothing away from the edges. */
export function autoScrollStep(y: number, box: { top: number; bottom: number }): number {
  const nearTop = y - box.top;
  const nearBottom = box.bottom - y;
  if (nearTop < EDGE_PX) return -Math.round(MAX_STEP_PX * Math.min(1, (EDGE_PX - nearTop) / EDGE_PX));
  if (nearBottom < EDGE_PX) return Math.round(MAX_STEP_PX * Math.min(1, (EDGE_PX - nearBottom) / EDGE_PX));
  return 0;
}

/** The nearest element above `element` that scrolls up and down, or null. */
export function scrollerOf(element: Element | null): HTMLElement | null {
  for (let current = element?.parentElement ?? null; current; current = current.parentElement) {
    const overflow = getComputedStyle(current).overflowY;
    if ((overflow === "auto" || overflow === "scroll") && current.scrollHeight > current.clientHeight) return current;
  }
  return null;
}
