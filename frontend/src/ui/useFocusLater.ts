import { useCallback, useEffect, useRef } from "react";
import { scrollBehaviour } from "./motion.js";

export interface FocusLaterOptions {
  /** Bring it into view as well: nearest, so a part already in sight doesn't move. */
  scroll?: boolean;
}

/**
 * Give focus to an element that the change being made will render: the
 * button a form gives way to, or the card a save puts in a list. `find` is
 * asked after each render until it gives an element, so focus lands once
 * the element is there, never on a frame's guess.
 */
export function useFocusLater(): (find: () => HTMLElement | null, options?: FocusLaterOptions) => void {
  const owed = useRef<{ find: () => HTMLElement | null; options: FocusLaterOptions } | null>(null);
  useEffect(() => {
    const target = owed.current?.find();
    if (!target || !owed.current) return;
    if (owed.current.options.scroll) target.scrollIntoView?.({ block: "nearest", behavior: scrollBehaviour() });
    owed.current = null;
    target.focus({ preventScroll: true });
  });
  return useCallback((find, options = {}) => {
    owed.current = { find, options };
  }, []);
}
