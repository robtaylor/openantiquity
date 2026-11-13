import { type RefObject, useEffect, useState } from "react";

/**
 * How far down the search slot's own control reaches, in pixels from the
 * slot's top: the search field, or the drawing guide in its place, folded or
 * not. The search results that open under the field don't count, so what
 * stacks below the slot stays put while they show. Null before it is
 * measured, and where the browser can't watch sizes.
 */
export function useSearchSlotHeight(slot: RefObject<HTMLElement | null>): number | null {
  const [height, setHeight] = useState<number | null>(null);
  useEffect(() => {
    const element = slot.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const measure = (): void => {
      const control = element.querySelector(".fc-draw-guide, .fc-search form");
      if (!control) return;
      setHeight(Math.round(control.getBoundingClientRect().bottom - element.getBoundingClientRect().top));
    };
    // The slot is as tall as what is in it, so it changes size whenever the control does or is swapped.
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [slot]);
  return height;
}
